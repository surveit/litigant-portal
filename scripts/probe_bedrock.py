import re

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from litigant_portal.agents.bedrock import _bedrock_client, model_class, model_tiers
from litigant_portal.app.selectors.bedrock import bedrock_policy


# The fork's Actions logs are public, so account ids and principal ARNs are masked.
def redact(text):
    text = re.sub(r"arn:aws[\w-]*:[^\s,;]+", "<arn>", text)
    return re.sub(r"\b\d{12}\b", "<account>", text)


def call(operation, fn):
    try:
        result = fn()
    except ClientError as error:
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = error.response.get("Error", {}).get("Code")
        message = redact(error.response.get("Error", {}).get("Message", ""))
        print(f"{operation}: FAILED {code} (HTTP {status}): {message}")
        return None
    except BotoCoreError as error:
        print(f"{operation}: FAILED {type(error).__name__}: {redact(str(error))}")
        return None
    print(f"{operation}: OK")
    return result


policy = bedrock_policy()
print(f"region={policy.region} key_set={bool(settings.BEDROCK_API_KEY.strip())}")
client = _bedrock_client(policy, settings.BEDROCK_API_KEY)
listed = call("ListFoundationModels", client.list_foundation_models)
call(
    "ListInferenceProfiles",
    lambda: client.list_inference_profiles(typeEquals="SYSTEM_DEFINED"),
)
enabled = {model.removeprefix("auto/") for model in model_tiers()}
candidates = [
    summary["modelId"]
    for summary in (listed or {}).get("modelSummaries", [])
    if (identity := model_class(summary["modelId"])) and identity[0] in enabled
]
print(f"enabled models listed: {len(candidates)}")
for model_id in candidates[:3]:
    availability = call(
        f"GetFoundationModelAvailability({model_id})",
        lambda: client.get_foundation_model_availability(modelId=model_id),
    )
    if availability:
        availability.pop("ResponseMetadata", None)
        print(f"  {redact(str(availability))}")
