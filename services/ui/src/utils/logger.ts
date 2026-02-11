import pino from 'pino';

const level = process.env.LOG_LEVEL || 'info';
const serviceName = process.env.SERVICE_NAME || 'ui-service';

export const logger = pino({
  level,
  base: {
    service_name: serviceName,
  },
  timestamp: pino.stdTimeFunctions.isoTime,
  formatters: {
    level: (label) => ({ level: label }),
  },
});

export const getLogger = (module: string) => logger.child({ module });
