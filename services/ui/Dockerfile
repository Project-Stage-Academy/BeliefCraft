FROM node:20-alpine AS deps

WORKDIR /app/services/ui

COPY services/ui/package.json ./package.json
RUN npm install


FROM node:20-alpine AS runtime

WORKDIR /app/services/ui

ENV NODE_ENV=development

COPY --from=deps /app/services/ui/node_modules ./node_modules
COPY services/ui ./

EXPOSE 3000

CMD ["sh", "-c", "npm run dev -- --hostname 0.0.0.0 --port ${PORT:-3000}"]
