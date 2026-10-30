package com.editographer.common.config;

import com.editographer.worker.api.WorkerTokenInterceptor;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** Web MVC setup. */
@Configuration
@EnableConfigurationProperties(AppProperties.class)
public class WebConfig implements WebMvcConfigurer {

  private static final String INTERNAL_PATHS = "/internal/**";
  private static final String WEB_APP = "forward:/index.html";

  private final AppProperties properties;

  public WebConfig(AppProperties properties) {
    this.properties = properties;
  }

  /** Lets a page refresh on an Angular route reach the app instead of a 404. */
  @Override
  public void addViewControllers(ViewControllerRegistry registry) {
    registry.addViewController("/projects/**").setViewName(WEB_APP);
    registry.addViewController("/renders/**").setViewName(WEB_APP);
  }

  @Override
  public void addInterceptors(InterceptorRegistry registry) {
    registry
        .addInterceptor(new WorkerTokenInterceptor(properties.workerToken()))
        .addPathPatterns(INTERNAL_PATHS);
  }
}
