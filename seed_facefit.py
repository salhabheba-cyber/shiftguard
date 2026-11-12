"""One-time, idempotent seed for the FaceFit Studio account (branch + admin).

Run with: python3 seed_facefit.py
Safe to re-run — skips any step that's already done.
"""
import secrets
import database

FACEFIT_THEME = {
    'primary':   'FA4B13',
    'secondary': 'FFF0E8',
    'accent':    'FF7A45',
    'dark':      '3D1704',
    'text':      '4A2A1A',
    'font':      'Poppins',
    'logo_text': 'FaceFit Studio',
    'logo_url':  '/static/images/facefit_logo.svg',
}
ADMIN_USERNAME = 'facefit_admin'

def main():
    database.init_db()

    branch = database.get_branch_by_slug('facefit')
    if branch:
        bid = branch['id']
        print(f"Branch 'FaceFit Studio' already exists (id={bid}, slug=facefit)")
    else:
        bid = database.add_branch('FaceFit Studio', slug='facefit',
                                  logo_url=FACEFIT_THEME['logo_url'])
        print(f"Created branch 'FaceFit Studio' (id={bid}, slug=facefit)")

    database.save_theme(bid, FACEFIT_THEME)
    print("Applied FaceFit theme (orange/Poppins)")

    if database.get_admin(ADMIN_USERNAME):
        print(f"Admin '{ADMIN_USERNAME}' already exists — not touching password")
    else:
        temp_password = secrets.token_urlsafe(9)
        database.create_admin(ADMIN_USERNAME, temp_password, role='admin', branch_id=bid)
        print(f"Created admin: {ADMIN_USERNAME} / {temp_password}")
        print("Change this password immediately after first login!")

if __name__ == '__main__':
    main()
