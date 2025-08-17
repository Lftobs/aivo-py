import sys
import asyncio
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - (AIVO-Main) - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the AIVO application."""
    if len(sys.argv) < 2:
        print("Usage: python main.py [recorder|scheduler]")
        sys.exit(1)

    module = sys.argv[1]

    if module == "recorder":
        try:
            from app.entry import main as recorder_main
            logger.info("🚀 Starting AIVO Recorder Service...")
            asyncio.run(recorder_main())
        except KeyboardInterrupt:
            logger.info("\n⏹️ Recorder interrupted by user.")
        except Exception as e:
            logger.error(f"❌ Fatal error in recorder: {e}")
            sys.exit(1)
        finally:
            logger.info("🔚 AIVO Recorder Service stopped.")

    elif module == "scheduler":
        try:
            from app.scheduler import main as scheduler_main
            logger.info("🚀 Starting AIVO Scheduler Service...")
            scheduler_main()
        except KeyboardInterrupt:
            logger.info("\n⏹️ Scheduler interrupted by user.")
        except Exception as e:
            logger.error(f"❌ Fatal error in scheduler: {e}")
            sys.exit(1)
        finally:
            logger.info("🔚 AIVO Scheduler Service stopped.")
    
    elif module == "health":
        print("AIVO is running. All systems operational.")
        sys.exit(0)

    else:
        print(f"Unknown module: {module}")
        sys.exit(1)


if __name__ == "__main__":
    main()
