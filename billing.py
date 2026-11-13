"""Stripe billing integration for business account subscriptions.

Fully wired but inert by default: every function checks
config.BILLING_ENABLED (set only once STRIPE_SECRET_KEY and
STRIPE_PRICE_ID are both configured) and returns a clear "not set up yet"
error instead of calling Stripe or crashing, so the rest of the app works
normally before real keys are added. Nothing here enforces a paywall —
subscription status is tracked and shown, not used to block access, until
that's turned on deliberately at the call site.
"""
import logging
import stripe
import config
import accounts

logger = logging.getLogger('shiftguard')

def _client():
    stripe.api_key = config.STRIPE_SECRET_KEY
    return stripe

def get_or_create_customer(acc):
    if acc.get('stripe_customer_id'):
        return acc['stripe_customer_id'], None
    try:
        customer = _client().Customer.create(
            name=acc['name'],
            email=acc.get('contact_email') or None,
            metadata={'account_id': str(acc['id']), 'slug': acc['slug']},
        )
    except stripe.StripeError as e:
        return None, _friendly_error(e)
    accounts.set_stripe_customer(acc['id'], customer.id)
    return customer.id, None

def create_checkout_session(acc, success_url, cancel_url):
    if not config.BILLING_ENABLED:
        return None, 'Billing is not set up yet'
    customer_id, err = get_or_create_customer(acc)
    if err: return None, err
    try:
        session = _client().checkout.Session.create(
            customer=customer_id,
            mode='subscription',
            line_items=[{'price': config.STRIPE_PRICE_ID, 'quantity': 1}],
            subscription_data={'trial_period_days': config.TRIAL_DAYS},
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
        )
    except stripe.StripeError as e:
        return None, _friendly_error(e)
    return session.url, None

def create_portal_session(acc, return_url):
    if not config.BILLING_ENABLED:
        return None, 'Billing is not set up yet'
    if not acc.get('stripe_customer_id'):
        return None, 'Subscribe first to manage billing'
    try:
        session = _client().billing_portal.Session.create(
            customer=acc['stripe_customer_id'],
            return_url=return_url,
        )
    except stripe.StripeError as e:
        return None, _friendly_error(e)
    return session.url, None

def _friendly_error(e):
    logger.error(f"Stripe error: {e}")
    return 'Billing is temporarily unavailable. Please try again shortly.'

def handle_webhook_event(payload, sig_header):
    """Verifies and applies a Stripe webhook event. Returns (event, error)."""
    if not config.BILLING_ENABLED:
        return None, 'Billing is not set up'
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, config.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError) as e:
        return None, str(e)

    etype = event['type']
    obj   = event['data']['object']

    if etype in ('customer.subscription.created', 'customer.subscription.updated'):
        acc = accounts.get_account_by_stripe_customer(obj['customer'])
        if acc:
            accounts.set_subscription_status(acc['id'], obj['id'], obj['status'])
    elif etype == 'customer.subscription.deleted':
        acc = accounts.get_account_by_stripe_customer(obj['customer'])
        if acc:
            accounts.set_subscription_status(acc['id'], obj['id'], 'canceled')

    return event, None
