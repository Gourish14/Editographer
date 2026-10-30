package com.editographer.common.logging;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.classic.spi.IThrowableProxy;
import ch.qos.logback.classic.spi.ThrowableProxyUtil;
import java.util.List;
import org.slf4j.event.KeyValuePair;
import org.springframework.boot.json.JsonWriter;
import org.springframework.boot.logging.structured.StructuredLogFormatter;

/**
 * Writes one JSON object per log line with the fields from the logging spec. Spec:
 * specs/11-coding-standards.md#6-logging-all-three-apps
 */
public final class JsonLogFormatter implements StructuredLogFormatter<ILoggingEvent> {

  private static final String SERVICE = "backend";

  private final JsonWriter<ILoggingEvent> writer =
      JsonWriter.<ILoggingEvent>of(
              members -> {
                members.add("ts", event -> event.getInstant().toString());
                members.add("level", event -> event.getLevel().toString());
                members.add("service", event -> SERVICE);
                members
                    .add(
                        LoggingConstants.REQUEST_ID,
                        event -> mdc(event, LoggingConstants.REQUEST_ID))
                    .whenNotNull();
                members
                    .add(LoggingConstants.JOB_ID, event -> mdc(event, LoggingConstants.JOB_ID))
                    .whenNotNull();
                members
                    .add(
                        LoggingConstants.RENDER_ID, event -> mdc(event, LoggingConstants.RENDER_ID))
                    .whenNotNull();
                members.add(LoggingConstants.EVENT, JsonLogFormatter::eventName);
                members.add("message", ILoggingEvent::getFormattedMessage);
                members
                    .add(
                        LoggingConstants.DURATION_MS,
                        event -> keyValue(event, LoggingConstants.DURATION_MS))
                    .whenNotNull();
                members
                    .add(
                        LoggingConstants.ERROR_CODE,
                        event -> keyValue(event, LoggingConstants.ERROR_CODE))
                    .whenNotNull();
                members.add("exception", JsonLogFormatter::stackTrace).whenNotNull();
              })
          .withNewLineAtEnd();

  @Override
  public String format(ILoggingEvent event) {
    return writer.writeToString(event);
  }

  private static String mdc(ILoggingEvent event, String key) {
    return event.getMDCPropertyMap().get(key);
  }

  private static String eventName(ILoggingEvent event) {
    Object explicit = keyValue(event, LoggingConstants.EVENT);
    return explicit != null ? explicit.toString() : event.getLoggerName();
  }

  private static Object keyValue(ILoggingEvent event, String key) {
    List<KeyValuePair> pairs = event.getKeyValuePairs();
    if (pairs == null) {
      return null;
    }
    return pairs.stream()
        .filter(pair -> key.equals(pair.key))
        .map(pair -> pair.value)
        .findFirst()
        .orElse(null);
  }

  private static String stackTrace(ILoggingEvent event) {
    IThrowableProxy proxy = event.getThrowableProxy();
    return proxy != null ? ThrowableProxyUtil.asString(proxy) : null;
  }
}
