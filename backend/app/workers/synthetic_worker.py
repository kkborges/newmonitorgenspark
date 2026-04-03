"""
Synthetic Test Worker — Executes URL, API, app flow, SSL and DNS checks.
"""
import asyncio
import logging
import ssl
import socket
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import httpx
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.synthetic_worker.dispatch_due_tests")
def dispatch_due_tests():
    """Find all synthetic tests that are due to run and dispatch them."""
    return run_async(_dispatch_due_tests_async())


async def _dispatch_due_tests_async():
    from app.db.base import AsyncSessionLocal
    from app.models import SyntheticTest
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    dispatched = 0

    async with AsyncSessionLocal() as db:
        tests_result = await db.execute(
            select(SyntheticTest).where(SyntheticTest.enabled == True)
        )
        tests = tests_result.scalars().all()

        for test in tests:
            # Check if test is due
            if test.last_check:
                next_run = test.last_check + timedelta(seconds=test.interval_seconds)
                if now < next_run:
                    continue

            # Dispatch appropriate worker
            if test.type.value == "ssl_check":
                run_ssl_check.apply_async(args=[test.id])
            elif test.type.value == "app_flow":
                run_app_flow.apply_async(args=[test.id])
            elif test.type.value == "api_monitor":
                run_api_monitor.apply_async(args=[test.id])
            else:
                run_url_monitor.apply_async(args=[test.id])

            dispatched += 1

    return {"dispatched": dispatched}


@celery_app.task(name="app.workers.synthetic_worker.run_url_monitor",
                 queue="synthetic")
def run_url_monitor(test_id: str):
    return run_async(_run_http_check(test_id, "url_monitor"))


@celery_app.task(name="app.workers.synthetic_worker.run_api_monitor",
                 queue="synthetic")
def run_api_monitor(test_id: str):
    return run_async(_run_http_check(test_id, "api_monitor"))


async def _run_http_check(test_id: str, check_type: str):
    from app.db.base import AsyncSessionLocal
    from app.models import SyntheticTest, SyntheticResult
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        test_result = await db.execute(select(SyntheticTest).where(SyntheticTest.id == test_id))
        test = test_result.scalar_one_or_none()
        if not test:
            return

        now = datetime.now(timezone.utc)
        result = SyntheticResult(
            id=str(uuid.uuid4()),
            test_id=test.id,
            tenant_id=test.tenant_id,
            timestamp=now,
            location="primary",
        )

        try:
            async with httpx.AsyncClient(
                timeout=test.timeout_seconds,
                follow_redirects=True,
                verify=True,
            ) as client:
                # Build request
                headers = test.headers or {}
                if test.auth_type == "bearer":
                    headers["Authorization"] = f"Bearer {test.auth_value}"
                elif test.auth_type == "api_key":
                    headers["X-API-Key"] = test.auth_value

                import time
                start = time.monotonic()
                resp = await client.request(
                    method=test.method or "GET",
                    url=test.url,
                    headers=headers,
                    content=test.body.encode() if test.body else None,
                )
                elapsed_ms = (time.monotonic() - start) * 1000

                result.status_code = resp.status_code
                result.response_time_ms = elapsed_ms
                result.response_headers = dict(resp.headers)
                result.response_body_snippet = resp.text[:500]

                # Run assertions for api_monitor
                assertions_passed = 0
                assertions_failed = 0
                assertion_details = []

                for assertion in (test.assertions or []):
                    a_type = assertion.get("type")
                    a_op = assertion.get("operator", "eq")
                    a_val = assertion.get("value")
                    passed = False
                    actual = None
                    error = None

                    try:
                        if a_type == "status_code":
                            actual = resp.status_code
                            passed = _compare(actual, a_op, int(a_val))
                        elif a_type == "response_time":
                            actual = elapsed_ms
                            passed = _compare(actual, a_op, float(a_val))
                        elif a_type == "body_contains":
                            actual = a_val
                            passed = a_val in resp.text
                        elif a_type == "header":
                            header_name = assertion.get("name", "")
                            actual = resp.headers.get(header_name, "")
                            passed = _compare(actual, a_op, a_val)
                        elif a_type == "json_path":
                            import json
                            from jsonpath_ng import parse as jp_parse
                            body = resp.json()
                            path = assertion.get("path", "$")
                            matches = jp_parse(path).find(body)
                            actual = [m.value for m in matches]
                            passed = len(matches) > 0 if a_op == "exists" else _compare(actual[0] if actual else None, a_op, a_val)
                    except Exception as e:
                        error = str(e)
                        passed = False

                    if passed:
                        assertions_passed += 1
                    else:
                        assertions_failed += 1

                    assertion_details.append({
                        "type": a_type, "operator": a_op, "expected": a_val,
                        "actual": str(actual), "passed": passed, "error": error
                    })

                result.assertions_passed = assertions_passed
                result.assertions_failed = assertions_failed
                result.assertion_details = assertion_details

                # Determine status
                is_ok = resp.status_code < 400 and assertions_failed == 0
                result.status = "up" if is_ok else "degraded" if assertions_failed > 0 else "down"

        except httpx.TimeoutException:
            result.status = "down"
            result.error_message = "Timeout"
        except Exception as e:
            result.status = "down"
            result.error_message = str(e)

        db.add(result)

        # Update test stats
        test.last_check = now
        test.last_status = result.status
        test.last_response_ms = result.response_time_ms

        await db.commit()

        # Create alert if failed
        if result.status == "down":
            _check_synthetic_alert.apply_async(args=[test.id])

        return {"test_id": test_id, "status": result.status, "response_ms": result.response_time_ms}


@celery_app.task(name="app.workers.synthetic_worker.run_ssl_check", queue="synthetic")
def run_ssl_check(test_id: str):
    return run_async(_run_ssl_check(test_id))


async def _run_ssl_check(test_id: str):
    from app.db.base import AsyncSessionLocal
    from app.models import SyntheticTest, SyntheticResult
    from sqlalchemy import select
    import ssl, socket
    from urllib.parse import urlparse

    async with AsyncSessionLocal() as db:
        test_result = await db.execute(select(SyntheticTest).where(SyntheticTest.id == test_id))
        test = test_result.scalar_one_or_none()
        if not test:
            return

        now = datetime.now(timezone.utc)
        result = SyntheticResult(
            id=str(uuid.uuid4()),
            test_id=test.id,
            tenant_id=test.tenant_id,
            timestamp=now,
        )

        try:
            parsed = urlparse(test.url)
            hostname = parsed.hostname
            port = parsed.port or 443

            ctx = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()

            # Parse certificate
            not_after = datetime.strptime(
                cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
            ).replace(tzinfo=timezone.utc)

            not_before = datetime.strptime(
                cert["notBefore"], "%b %d %H:%M:%S %Y %Z"
            ).replace(tzinfo=timezone.utc)

            days_remaining = (not_after - now).days
            issuer = dict(x[0] for x in cert.get("issuer", []))
            subject = dict(x[0] for x in cert.get("subject", []))

            result.ssl_valid = True
            result.ssl_expires_at = not_after
            result.ssl_days_remaining = days_remaining
            result.ssl_issuer = issuer.get("organizationName", issuer.get("commonName", ""))
            result.ssl_subject = subject.get("commonName", "")

            warn_days = test.ssl_warn_days or 30
            crit_days = test.ssl_crit_days or 7

            if days_remaining <= 0:
                result.status = "down"
                result.error_message = "Certificate expired"
            elif days_remaining <= crit_days:
                result.status = "degraded"
                result.error_message = f"Certificate expires in {days_remaining} days (critical)"
            elif days_remaining <= warn_days:
                result.status = "degraded"
                result.error_message = f"Certificate expires in {days_remaining} days (warning)"
            else:
                result.status = "up"

        except ssl.SSLCertVerificationError as e:
            result.ssl_valid = False
            result.status = "down"
            result.error_message = f"SSL verification failed: {e}"
        except Exception as e:
            result.status = "down"
            result.error_message = str(e)

        db.add(result)
        test.last_check = now
        test.last_status = result.status
        await db.commit()

        return {
            "test_id": test_id,
            "status": result.status,
            "days_remaining": result.ssl_days_remaining,
            "expires_at": result.ssl_expires_at.isoformat() if result.ssl_expires_at else None,
        }


@celery_app.task(name="app.workers.synthetic_worker.run_app_flow", queue="synthetic")
def run_app_flow(test_id: str):
    """Execute Playwright-based app flow test."""
    return run_async(_run_app_flow(test_id))


async def _run_app_flow(test_id: str):
    from app.db.base import AsyncSessionLocal
    from app.models import SyntheticTest, SyntheticResult
    from sqlalchemy import select
    import time

    async with AsyncSessionLocal() as db:
        test_result = await db.execute(select(SyntheticTest).where(SyntheticTest.id == test_id))
        test = test_result.scalar_one_or_none()
        if not test:
            return

        now = datetime.now(timezone.utc)
        result = SyntheticResult(
            id=str(uuid.uuid4()),
            test_id=test.id,
            tenant_id=test.tenant_id,
            timestamp=now,
        )

        try:
            from playwright.async_api import async_playwright

            steps = test.flow_steps or []
            step_details = []
            steps_passed = 0

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                start = time.monotonic()

                for i, step in enumerate(steps):
                    step_result = {"step": i + 1, "action": step.get("action"), "passed": False}
                    try:
                        action = step.get("action")
                        if action == "navigate":
                            await page.goto(step["url"], timeout=test.timeout_seconds * 1000)
                        elif action == "click":
                            await page.click(step["selector"], timeout=5000)
                        elif action == "fill":
                            await page.fill(step["selector"], step["value"])
                        elif action == "wait":
                            await page.wait_for_selector(step["selector"], timeout=5000)
                        elif action == "assert_text":
                            text = await page.text_content(step["selector"])
                            assert step["value"] in (text or "")
                        elif action == "assert_url":
                            assert step["value"] in page.url
                        elif action == "screenshot":
                            pass  # could upload to S3

                        step_result["passed"] = True
                        steps_passed += 1
                    except Exception as e:
                        step_result["error"] = str(e)
                    step_details.append(step_result)

                elapsed_ms = (time.monotonic() - start) * 1000
                await browser.close()

            result.steps_total = len(steps)
            result.steps_passed = steps_passed
            result.step_details = step_details
            result.response_time_ms = elapsed_ms
            result.status = "up" if steps_passed == len(steps) else ("degraded" if steps_passed > 0 else "down")

        except Exception as e:
            result.status = "down"
            result.error_message = str(e)

        db.add(result)
        test.last_check = now
        test.last_status = result.status
        await db.commit()
        return {"test_id": test_id, "status": result.status}


@celery_app.task(name="app.workers.synthetic_worker.check_synthetic_alert")
def _check_synthetic_alert(test_id: str):
    """Create alert if synthetic test is consistently failing."""
    pass   # Implemented in alert_worker


def _compare(actual, op: str, expected) -> bool:
    try:
        if op == "eq": return actual == expected
        if op == "ne": return actual != expected
        if op == "gt": return float(actual) > float(expected)
        if op == "lt": return float(actual) < float(expected)
        if op == "gte": return float(actual) >= float(expected)
        if op == "lte": return float(actual) <= float(expected)
        if op == "contains": return str(expected) in str(actual)
        if op == "not_contains": return str(expected) not in str(actual)
        if op == "exists": return actual is not None
        return False
    except Exception:
        return False
