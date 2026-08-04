import os, json, urllib.request
import stripe

base = os.environ["INTEGRATION_PROXY_URL"]
job_id = "e8ebec83-59ad-495d-b7e4-dfc022d1558c"
key = "sk-emergent-aF311793c8970740f8"

req = urllib.request.Request(
    base + "/stripe/sandboxes",
    data=json.dumps({"job_id": job_id}).encode(),
    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as r:
    sandbox = json.load(r)

print("ONBOARDING_URL:", sandbox.get("onboarding_url"))

env_path = os.path.join(os.path.dirname(__file__), ".env")
lines = open(env_path).read().splitlines()
keep = [l for l in lines if not l.startswith(("STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "STRIPE_ACCOUNT_ID", "STRIPE_WEBHOOK_SECRET", "STRIPE_MODE"))]
keep += [
    f'STRIPE_SECRET_KEY="{sandbox["sandbox_secret_key"]}"',
    f'STRIPE_PUBLISHABLE_KEY="{sandbox["sandbox_publishable_key"]}"',
    f'STRIPE_ACCOUNT_ID="{sandbox["sandbox_account_id"]}"',
    f'STRIPE_WEBHOOK_SECRET="{sandbox["preview_webhook_secret"]}"',
    'STRIPE_MODE="test"',
]
open(env_path, "w").write("\n".join(keep) + "\n")

stripe.api_key = sandbox["sandbox_secret_key"]

# Catalog: Pro Plan $149/mo SaaS
def get_or_create_product():
    for p in stripe.Product.list(active=True).auto_paging_iter():
        if p.to_dict().get("metadata", {}).get("emergent_product_id") == "pro_plan":
            return p
    return stripe.Product.create(name="Pro Plan", tax_code="txcd_10103001",
        metadata={"managed_by": "emergent", "emergent_product_id": "pro_plan"})

product = get_or_create_product()
existing = stripe.Price.list(lookup_keys=["pro_monthly"], active=True, limit=1).data
if existing and (existing[0].unit_amount != 14900 or existing[0].currency != "usd"):
    stripe.Price.modify(existing[0].id, active=False)
    existing = []
if not existing:
    stripe.Price.create(product=product.id, unit_amount=14900, currency="usd",
        lookup_key="pro_monthly", transfer_lookup_key=True, recurring={"interval": "month"})
print("CATALOG_DONE")
