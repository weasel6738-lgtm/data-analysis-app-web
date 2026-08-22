"""Lazy adapters for Microsoft Agent Framework and GitHub Copilot SDK.

Both integrations are real execution paths but remain optional. Production can
install ``requirements-ai.txt`` and configure credentials; local/demo mode never
sends uploaded manufacturing data to an external provider.
"""

from __future__ import annotations

import importlib.util
import json
from typing import Any

from .config import Settings


class IntegrationError(RuntimeError):
    """An external AI provider was selected but could not complete its task."""


def integration_status(settings: Settings) -> dict[str, Any]:
    return {
        "orchestrator": {
            "provider": settings.orchestrator_provider,
            "sdkInstalled": importlib.util.find_spec("agent_framework") is not None,
            "configured": bool(
                settings.azure_openai_endpoint and settings.azure_openai_deployment
            ),
        },
        "drafting": {
            "provider": settings.draft_provider,
            "sdkInstalled": importlib.util.find_spec("copilot") is not None,
            "configured": bool(settings.github_token),
        },
        "demoMode": settings.orchestrator_provider == "local"
        and settings.draft_provider == "local",
        "dataPolicy": "External providers are called only when explicitly configured.",
    }


async def run_microsoft_agent(prompt: str, settings: Settings) -> str:
    if importlib.util.find_spec("agent_framework") is None:
        raise IntegrationError(
            "Microsoft Agent Framework 패키지가 없습니다. requirements-ai.txt를 설치하세요."
        )
    if not settings.azure_openai_endpoint or not settings.azure_openai_deployment:
        raise IntegrationError(
            "AZURE_OPENAI_ENDPOINT와 AZURE_OPENAI_DEPLOYMENT를 설정하세요."
        )
    try:
        from agent_framework.azure import AzureOpenAIChatClient

        credential = None
        kwargs: dict[str, Any] = {
            "endpoint": settings.azure_openai_endpoint,
            "deployment_name": settings.azure_openai_deployment,
        }
        if settings.azure_openai_api_key:
            kwargs["api_key"] = settings.azure_openai_api_key
        else:
            from azure.identity.aio import DefaultAzureCredential

            credential = DefaultAzureCredential()
            kwargs["credential"] = credential
        client = AzureOpenAIChatClient(**kwargs)
        agent = client.create_agent(
            instructions=(
                "You orchestrate semiconductor manufacturing analysis. Distinguish "
                "observations, hypotheses, and required verification. Answer in Korean."
            )
        )
        try:
            result = await agent.run(prompt)
            return str(result)
        finally:
            if credential is not None:
                await credential.close()
    except IntegrationError:
        raise
    except Exception as exc:
        raise IntegrationError(f"Microsoft Agent Framework 실행 실패: {exc}") from exc


async def run_copilot_draft(prompt: str, settings: Settings) -> str:
    if importlib.util.find_spec("copilot") is None:
        raise IntegrationError(
            "GitHub Copilot SDK 패키지가 없습니다. requirements-ai.txt를 설치하세요."
        )
    try:
        from copilot import CopilotClient

        client = CopilotClient()
        await client.start()
        try:
            session = await client.create_session(
                {"model": settings.copilot_model, "streaming": False}
            )
            response = await session.send_and_wait({"prompt": prompt})
            data = getattr(response, "data", response)
            content = getattr(data, "content", None)
            if not content:
                content = json.dumps(data, ensure_ascii=False, default=str)
            return str(content)
        finally:
            await client.stop()
    except IntegrationError:
        raise
    except Exception as exc:
        raise IntegrationError(f"GitHub Copilot SDK 실행 실패: {exc}") from exc
