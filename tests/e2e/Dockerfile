#
# End-to-end tests of Agilina in a real browser (Playwright, Chromium).
#
# It runs on the host's network so that the browser reaches the application the way a person
# does: http://localhost:4200 for the web and http://localhost:8080 for Keycloak (that is the
# address the web is configured with, and the issuer of the tokens).
#
# Build context: tests/e2e.
ARG NODE_VERSION=22
FROM node:${NODE_VERSION}-bookworm-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
# The browser and the system libraries it needs, for the version of Playwright in the lock file.
RUN npx playwright install --with-deps chromium
COPY . .
CMD ["npx", "playwright", "test"]
