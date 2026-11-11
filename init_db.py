import accounts, config, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("="*50)
    logger.info("ShiftGuard - Database Init")
    logger.info("="*50)
    # Creates the platform tables, registers the original database as the
    # first account (keeping all its data), creates the owner login and
    # brings every account database up to date. Safe to run more than once.
    accounts.init_platform()
    logger.info("✓ Ready!")
    logger.info("  Home:  http://localhost:5000  (click Account to sign in)")
    logger.info(f"  Owner: {config.OWNER_EMAIL}")
    logger.info("  First business: admin / admin123")
    logger.info("="*50)

if __name__ == '__main__': main()
