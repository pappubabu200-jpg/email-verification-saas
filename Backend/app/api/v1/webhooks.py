@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    # ... existing verification code ...

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer = session["customer"]
        price_id = session["subscription"]  # subscription object

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.stripe_customer_id == customer).first()
            if not user:
                raise ValueError("user_not_found")

            # MAP price → plan
            if session["mode"] == "subscription":
                price = session["display_items"][0]["price"]["id"] \
                    if "display_items" in session else None

                plan_name = None
                if price == settings.STRIPE_PRICE_PRO:
                    plan_name = "pro"
                elif price == settings.STRIPE_PRICE_TEAM:
                    plan_name = "team"
                elif price == settings.STRIPE_PRICE_ENTERPRISE:
                    plan_name = "enterprise"

                if plan_name:
                    user.plan = plan_name
                    db.add(user)
                    db.commit()
        finally:
            db.close()
