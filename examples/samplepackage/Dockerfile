FROM agentflow-runner:latest

# Install package-specific dependencies
# RUN pip install --user your-deps-here

# Pre-copy the agent code (optional - or still use zip at runtime)
COPY --chown=runner:runner . /workspace/code/

WORKDIR /workspace/code
