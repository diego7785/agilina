#
# End-to-end tests of Agilina in a real browser (Playwright: Chromium, and Firefox for the room).
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
# The browsers and the system libraries they need, for the version of Playwright in the lock file.
# Firefox is only for the room of the daily (AGI-60); a layer of its own keeps Chromium's cached.
RUN npx playwright install --with-deps chromium
RUN npx playwright install --with-deps firefox
COPY . .
CMD ["npx", "playwright", "test"]
