#!/usr/bin/env python3
"""Re-apply the local OpenAI Ultrafast billing customization after an upstream merge.

The operations are idempotent. Running it on a tree that already contains the
feature must not duplicate fields, SQL, or UI controls.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def write_if_changed(path: str, text: str) -> None:
    target = ROOT / path
    if target.exists() and target.read_text() == text:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    print(f"updated {path}")


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    if not target.exists():
        print(f"skip missing {path}")
        return
    text = target.read_text()
    if new in text:
        return
    if old not in text:
        print(f"skip {path}: anchor not found")
        return
    write_if_changed(path, text.replace(old, new, 1))


def ensure_file(path: str, content: str) -> None:
    target = ROOT / path
    if target.exists():
        return
    write_if_changed(path, content)


def main() -> None:
    ensure_file(
        "backend/migrations/246_group_force_openai_ultrafast.sql",
        """ALTER TABLE groups
    ADD COLUMN IF NOT EXISTS force_openai_ultrafast BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN groups.force_openai_ultrafast IS
    'Bill OpenAI requests in this group at the Ultrafast (6x) tier even when the upstream reports a cheaper service_tier';
""",
    )
    replace_once(
        "backend/ent/schema/group.go",
        '''field.Bool("free_openai_fast").
			Default(false).
			Comment("是否让此 OpenAI/Composite 分组的 Fast 请求按 Standard 价格计费"),''',
        '''field.Bool("free_openai_fast").
			Default(false).
			Comment("是否让此 OpenAI/Composite 分组的 Fast 请求按 Standard 价格计费"),
		field.Bool("force_openai_ultrafast").
			Default(false).
			Comment("是否让此 OpenAI/Composite 分组按 Ultrafast（6 倍）价格计费"),''',
    )
    replace_once(
        "backend/internal/service/group.go",
        "\tFreeOpenAIFast              bool // OpenAI Fast 请求按 Standard 价格向用户计费\n",
        "\tFreeOpenAIFast              bool // OpenAI Fast 请求按 Standard 价格向用户计费\n\tForceOpenAIUltrafast        bool // OpenAI 请求按 Ultrafast（6 倍）价格计费，不受上游降档影响\n",
    )
    replace_once(
        "backend/internal/service/billing_service.go",
        "if isOpenAIGPT6AstraModel(normalized) {\n\t\tcloned.UltrafastMultiplier = 6\n\t}",
        "if isOpenAIGPT6AstraModel(normalized) || openai.IsGPT61SolModelSpelling(normalized) || openai.IsGPT6SolOrLunaModelSpelling(normalized) {\n\t\tcloned.UltrafastMultiplier = 6\n\t}",
    )
    replace_once(
        "backend/internal/service/openai_gateway_usage.go",
        "\tlogServiceTierBillingDowngrade(\"service.openai_gateway\", account, result.RequestID, ApplyOpenAIServiceTierBillingResolution(billingAccount, result))\n",
        """\tresolution := ApplyOpenAIServiceTierBillingResolution(billingAccount, result)
	logServiceTierBillingDowngrade("service.openai_gateway", account, result.RequestID, resolution)
	if groupBillsOpenAIUltrafast(apiKey, billingAccount) {
		tier := OpenAIFastTierUltrafast
		result.ServiceTier = &tier
	}
""",
    )
    usage = ROOT / "backend/internal/service/openai_gateway_usage.go"
    if usage.exists() and "func groupBillsOpenAIUltrafast(" not in usage.read_text():
        replace_once(
            "backend/internal/service/openai_gateway_usage.go",
            "func groupBillsOpenAIFastAtStandard(",
            """func groupBillsOpenAIUltrafast(apiKey *APIKey, account *Account) bool {
	if apiKey == nil || apiKey.Group == nil || !apiKey.Group.ForceOpenAIUltrafast {
		return false
	}
	if account == nil || !account.IsOpenAI() {
		return false
	}
	return groupSupportsOpenAIFast(apiKey.Group.Platform)
}

func groupBillsOpenAIFastAtStandard(""",
        )
    print("ultrafast patch check complete")


if __name__ == "__main__":
    main()
