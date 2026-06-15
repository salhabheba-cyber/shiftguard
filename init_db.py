import database, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("="*50)
    logger.info("ShiftGuard - Database Init")
    logger.info("="*50)
    database.init_db()
    logger.info("✓ Tables created")
    if not database.get_admin('admin'):
        database.create_admin('admin','admin123',role='superadmin')
        logger.warning("✓ Admin created: username=admin  password=admin123")
    else:
        logger.info("✓ Admin user already exists")
    logger.info("="*50)
    logger.info("✓ Ready!")
    logger.info("  Kiosk: http://localhost:5000/kiosk")
    logger.info("  Admin: http://localhost:5000/admin")
    logger.info("  Login: admin / admin123")
    logger.info("="*50)

if __name__ == '__main__': main()
