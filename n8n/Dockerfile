FROM n8nio/n8n:1.110.1
# Workflow exports are baked into the image (no bind mount needed), imported once by the n8n-import service
COPY --chown=node:node workflows /workflows
