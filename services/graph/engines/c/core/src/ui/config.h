/*
 * config.h — HTTP 服务持久化配置（ui_enabled / ui_port）。
 *
 * 写入缓存目录下的 config.json（缓存根可由 ENGINE_CACHE_DIR 覆盖）。
 * 线程安全：load/save 为独立的文件系统操作。
 */
#ifndef ENGINE_UI_CONFIG_H
#define ENGINE_UI_CONFIG_H

#include <stdbool.h>

/* Default values */
/* 默认 sidecar 端口（API 侧经 GRAPH_ENGINE_URL 对接） */
#define ENGINE_UI_DEFAULT_PORT 9750
#define ENGINE_UI_DEFAULT_ENABLED false

typedef struct {
    bool ui_enabled;
    int ui_port;
} engine_ui_config_t;

/* Load config from disk. Missing/corrupt file → defaults. */
void engine_ui_config_load(engine_ui_config_t *cfg);

/* Atomically save one complete config generation. Creates the directory if
 * needed and reports write/sync/replace failures. */
bool engine_ui_config_save(const engine_ui_config_t *cfg);

/* Get the config file path. Writes to buf (up to bufsz bytes).
 * Exposed for testing. */
void engine_ui_config_path(char *buf, int bufsz);

#endif /* ENGINE_UI_CONFIG_H */
