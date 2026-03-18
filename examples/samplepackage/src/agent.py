import logging
import subprocess
from platform_sdk import step

log = logging.getLogger("hello")

@step("greet")
def greet():
    log.info("Hello from agent")
    subprocess.run(["python", "-c", "print('subprocess says hi')"], check=True)

def main():
    greet()
    log.info("Done")

if __name__ == "__main__":
    main()