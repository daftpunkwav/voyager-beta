/*
 * language.c — Language detection from filename and extension.
 *
 * Maps file extensions and special filenames to EngineLanguage enum values.
 * Handles .m disambiguation (Objective-C vs MATLAB).
 * Consults the process-global user config (set via engine_set_user_lang_config)
 * before the built-in lookup table.
 */
#include "discover/discover.h"
#include "discover/userconfig.h"
#include "engine.h" // EngineLanguage, ENGINE_LANG_*

#include "foundation/constants.h"
#include "foundation/compat_fs.h"

enum { LANG_SCAN_PASSES = 2 };
#define SLEN(s) (sizeof(s) - 1)
#include <ctype.h>
#include <stdio.h>
#include <string.h>

/* ── Extension → Language lookup table ───────────────────────────── */

typedef struct {
    const char *ext; /* including dot, e.g. ".go" */
    EngineLanguage language;
} ext_entry_t;

/* Sorted by extension for binary search (but linear scan is fine for ~120 entries) */
static const ext_entry_t EXT_TABLE[] = {
    /* Bash */
    {".bash", ENGINE_LANG_BASH},
    {".sh", ENGINE_LANG_BASH},

    /* C */
    {".c", ENGINE_LANG_C},

    /* C++ */
    {".cc", ENGINE_LANG_CPP},
    {".ccm", ENGINE_LANG_CPP},
    {".cpp", ENGINE_LANG_CPP},
    {".cppm", ENGINE_LANG_CPP},
    {".cxx", ENGINE_LANG_CPP},
    {".h", ENGINE_LANG_CPP},
    {".hh", ENGINE_LANG_CPP},
    {".hpp", ENGINE_LANG_CPP},
    {".hxx", ENGINE_LANG_CPP},
    {".ixx", ENGINE_LANG_CPP},

    /* C# */
    {".cs", ENGINE_LANG_CSHARP},

    /* Clojure */
    {".clj", ENGINE_LANG_CLOJURE},
    {".cljc", ENGINE_LANG_CLOJURE},
    {".cljs", ENGINE_LANG_CLOJURE},

    /* CMake */
    {".cmake", ENGINE_LANG_CMAKE},

    /* Common Lisp */
    {".cl", ENGINE_LANG_COMMONLISP},
    {".lisp", ENGINE_LANG_COMMONLISP},
    {".lsp", ENGINE_LANG_COMMONLISP},

    /* CSS */
    {".css", ENGINE_LANG_CSS},

    /* CUDA */
    {".cu", ENGINE_LANG_CUDA},
    {".cuh", ENGINE_LANG_CUDA},

    /* Dart */
    {".dart", ENGINE_LANG_DART},

    /* Dockerfile */
    {".dockerfile", ENGINE_LANG_DOCKERFILE},

    /* Elixir */
    {".ex", ENGINE_LANG_ELIXIR},
    {".exs", ENGINE_LANG_ELIXIR},

    /* DotEnv */
    {".env", ENGINE_LANG_DOTENV},

    /* Elm */
    {".elm", ENGINE_LANG_ELM},

    /* Emacs Lisp */
    {".el", ENGINE_LANG_EMACSLISP},

    /* Erlang */
    {".erl", ENGINE_LANG_ERLANG},

    /* F# */
    {".fs", ENGINE_LANG_FSHARP},
    {".fsi", ENGINE_LANG_FSHARP},
    {".fsx", ENGINE_LANG_FSHARP},

    /* Fortran */
    {".f03", ENGINE_LANG_FORTRAN},
    {".f08", ENGINE_LANG_FORTRAN},
    {".f90", ENGINE_LANG_FORTRAN},
    {".f95", ENGINE_LANG_FORTRAN},

    /* GLSL */
    {".frag", ENGINE_LANG_GLSL},
    {".glsl", ENGINE_LANG_GLSL},
    {".vert", ENGINE_LANG_GLSL},

    /* Go */
    {".go", ENGINE_LANG_GO},

    /* GraphQL */
    {".gql", ENGINE_LANG_GRAPHQL},
    {".graphql", ENGINE_LANG_GRAPHQL},

    /* Groovy */
    {".gradle", ENGINE_LANG_GROOVY},
    {".groovy", ENGINE_LANG_GROOVY},

    /* Haskell */
    {".hs", ENGINE_LANG_HASKELL},

    /* HCL / Terraform */
    {".hcl", ENGINE_LANG_HCL},
    {".tf", ENGINE_LANG_HCL},

    /* HTML */
    {".htm", ENGINE_LANG_HTML},
    {".html", ENGINE_LANG_HTML},

    /* INI */
    {".cfg", ENGINE_LANG_INI},
    {".conf", ENGINE_LANG_INI},
    {".ini", ENGINE_LANG_INI},

    /* Java */
    {".java", ENGINE_LANG_JAVA},

    /* JavaScript */
    {".js", ENGINE_LANG_JAVASCRIPT},
    {".jsx", ENGINE_LANG_JAVASCRIPT},
    {".mjs", ENGINE_LANG_JAVASCRIPT}, /* ES modules (#197) */
    {".cjs", ENGINE_LANG_JAVASCRIPT}, /* CommonJS modules */

    /* JSON */
    {".json", ENGINE_LANG_JSON},

    /* Julia */
    {".jl", ENGINE_LANG_JULIA},

    /* Kotlin */
    {".kt", ENGINE_LANG_KOTLIN},
    {".kts", ENGINE_LANG_KOTLIN},


    /* Lua */
    {".lua", ENGINE_LANG_LUA},


    /* Makefile */
    {".mk", ENGINE_LANG_MAKEFILE},

    /* Markdown */
    {".md", ENGINE_LANG_MARKDOWN},
    {".mdx", ENGINE_LANG_MARKDOWN},

    /* MATLAB */
    {".m", ENGINE_LANG_MATLAB},
    {".matlab", ENGINE_LANG_MATLAB},
    {".mlx", ENGINE_LANG_MATLAB},

    /* Meson */
    {".meson", ENGINE_LANG_MESON},

    /* Mojo */
    {".mojo", ENGINE_LANG_MOJO},

    /* Nix */
    {".nix", ENGINE_LANG_NIX},

    /* OCaml */
    {".ml", ENGINE_LANG_OCAML},
    {".mli", ENGINE_LANG_OCAML},

    /* Perl */
    {".pl", ENGINE_LANG_PERL},
    {".pm", ENGINE_LANG_PERL},

    /* PHP */
    {".php", ENGINE_LANG_PHP},

    /* Protobuf */
    {".proto", ENGINE_LANG_PROTOBUF},

    /* Python */
    {".py", ENGINE_LANG_PYTHON},

    /* R — case insensitive handled separately */
    {".R", ENGINE_LANG_R},
    {".r", ENGINE_LANG_R},

    /* Ruby */
    {".gemspec", ENGINE_LANG_RUBY},
    {".rake", ENGINE_LANG_RUBY},
    {".rb", ENGINE_LANG_RUBY},

    /* Rust */
    {".rs", ENGINE_LANG_RUST},

    /* Scala */
    {".sc", ENGINE_LANG_SCALA},
    {".scala", ENGINE_LANG_SCALA},

    /* SCSS */
    {".scss", ENGINE_LANG_SCSS},

    /* SQL */
    {".sql", ENGINE_LANG_SQL},

    /* Svelte */
    {".svelte", ENGINE_LANG_SVELTE},

    /* Swift */
    {".swift", ENGINE_LANG_SWIFT},

    /* SystemVerilog + Verilog */
    {".sv", ENGINE_LANG_VERILOG},
    {".v", ENGINE_LANG_VERILOG},

    /* TOML */
    {".toml", ENGINE_LANG_TOML},

    /* TSX */
    {".tsx", ENGINE_LANG_TSX},

    /* TypeScript */
    {".ts", ENGINE_LANG_TYPESCRIPT},
    {".mts", ENGINE_LANG_TYPESCRIPT}, /* TS ES modules */
    {".cts", ENGINE_LANG_TYPESCRIPT}, /* TS CommonJS modules */

    /* VimScript */
    {".vim", ENGINE_LANG_VIMSCRIPT},
    {".vimrc", ENGINE_LANG_VIMSCRIPT},
    {"BUILD", ENGINE_LANG_STARLARK},
    {"BUILD.bazel", ENGINE_LANG_STARLARK},
    {"WORKSPACE", ENGINE_LANG_STARLARK},
    {"WORKSPACE.bazel", ENGINE_LANG_STARLARK},

    /* .inc：常见于 C/C++ 头文件片段；BitBake 语法已移除。 */

    /* Vue */
    {".vue", ENGINE_LANG_VUE},


    /* XML */
    {".xml", ENGINE_LANG_XML},
    {".xsd", ENGINE_LANG_XML},
    {".xsl", ENGINE_LANG_XML},
    {".svg", ENGINE_LANG_XML},

    /* YAML */
    {".yaml", ENGINE_LANG_YAML},
    {".yml", ENGINE_LANG_YAML},

    /* Ada */
    {".adb", ENGINE_LANG_ADA},

    /* Ada */
    {".ads", ENGINE_LANG_ADA},


    /* Astro */
    {".astro", ENGINE_LANG_ASTRO},

    /* AWK */
    {".awk", ENGINE_LANG_AWK},

    /* BitBake */

    /* BitBake */

    /* BitBake */


    /* BibTeX */

    /* Bicep */
    {".bicep", ENGINE_LANG_BICEP},

    /* Blade */
    /* .blade.php handled by userconfig compound extensions, not EXT_TABLE */

    /* Starlark */
    {".bzl", ENGINE_LANG_STARLARK},

    /* Cairo */

    /* Cap'n Proto */

    /* Apex */
    {".cls", ENGINE_LANG_APEX},

    /* Crystal */

    /* CSV */

    /* D */
    {".d", ENGINE_LANG_DLANG},

    /* Diff */

    /* Pascal */
    {".dpr", ENGINE_LANG_PASCAL},

    /* DeviceTree */

    /* DeviceTree */


    /* Fish */
    {".fish", ENGINE_LANG_FISH},

    /* Fennel */

    /* HLSL */
    {".fx", ENGINE_LANG_HLSL},

    /* GDScript */
    {".gd", ENGINE_LANG_GDSCRIPT},

    /* Gleam */
    {".gleam", ENGINE_LANG_GLEAM},

    /* GN */

    /* GN */

    /* Go Template */
    {".gotmpl", ENGINE_LANG_GOTEMPLATE},
    {".tpl", ENGINE_LANG_GOTEMPLATE}, /* Helm _helpers.tpl named-template definitions */



    /* HLSL */
    {".hlsl", ENGINE_LANG_HLSL},

    /* HLSL */
    {".hlsli", ENGINE_LANG_HLSL},

    /* ISPC */

    /* Jinja2 */
    {".j2", ENGINE_LANG_JINJA2},

    /* Janet */

    /* Jinja2 */
    {".jinja", ENGINE_LANG_JINJA2},

    /* Jinja2 */
    {".jinja2", ENGINE_LANG_JINJA2},

    /* JSON5 */

    /* Jsonnet */
    {".jsonnet", ENGINE_LANG_JSONNET},

    /* KDL */

    /* Linker Script */

    /* Linker Script */

    /* Jsonnet */
    {".libsonnet", ENGINE_LANG_JSONNET},

    /* Liquid */
    {".liquid", ENGINE_LANG_LIQUID},

    /* LLVM IR */
    {".ll", ENGINE_LANG_LLVM_IR},

    /* Pascal */
    {".lpr", ENGINE_LANG_PASCAL},

    /* Luau */

    /* Qt QML */
    {".qml", ENGINE_LANG_QML},

    /* CFML / ColdFusion — .cfc components are script-dialect; .cfm are tag templates */

    /* Mermaid */
    {".mermaid", ENGINE_LANG_MERMAID},

    /* Mermaid */
    {".mmd", ENGINE_LANG_MERMAID},

    /* Move */

    /* NASM */
    {".nasm", ENGINE_LANG_NASM},

    /* Nickel */

    /* Nim */

    /* Nim */

    /* Squirrel */

    /* Odin */
    {".odin", ENGINE_LANG_ODIN},

    /* DeviceTree */

    /* Pascal */
    {".pas", ENGINE_LANG_PASCAL},

    /* Diff */

    /* Pine Script */

    /* Pkl */

    /* PO */


    /* PO */

    /* Puppet */
    {".pp", ENGINE_LANG_PUPPET},

    /* Prisma */
    {".prisma", ENGINE_LANG_PRISMA},

    /* Properties */
    {".properties", ENGINE_LANG_PROPERTIES},

    /* PowerShell */
    {".ps1", ENGINE_LANG_POWERSHELL},

    /* PowerShell */
    {".psd1", ENGINE_LANG_POWERSHELL},

    /* PowerShell */
    {".psm1", ENGINE_LANG_POWERSHELL},

    /* PureScript */

    /* ReScript */

    /* ReScript */

    /* Regex */

    /* Racket */
    {".rkt", ENGINE_LANG_RACKET},

    /* RON */

    /* reStructuredText */
    {".rst", ENGINE_LANG_RST},

    /* Assembly */
    {".s", ENGINE_LANG_ASSEMBLY},

    /* Assembly */
    {".S", ENGINE_LANG_ASSEMBLY},

    /* Scheme */
    {".scm", ENGINE_LANG_SCHEME},

    /* Slang */

    /* Smali */

    /* Smithy */

    /* Solidity */
    {".sol", ENGINE_LANG_SOLIDITY},



    /* Scheme */
    {".ss", ENGINE_LANG_SCHEME},

    /* Starlark */
    {".star", ENGINE_LANG_STARLARK},



    /* Sway */

    /* Tcl */
    {".tcl", ENGINE_LANG_TCL},

    /* TableGen */

    /* Templ */

    /* Thrift */

    /* Teal */


    /* Go Template */
    {".tmpl", ENGINE_LANG_GOTEMPLATE},

    /* Apex */
    {".trigger", ENGINE_LANG_APEX},

    /* Typst */
    {".typ", ENGINE_LANG_TYPST},

    /* VHDL */
    {".vhd", ENGINE_LANG_VHDL},

    /* VHDL */
    {".vhdl", ENGINE_LANG_VHDL},

    /* WGSL */
    {".wgsl", ENGINE_LANG_WGSL},

    /* WIT */

    /* Zsh */
    {".zsh", ENGINE_LANG_ZSH},

    /* Zig */
    {".zig", ENGINE_LANG_ZIG},
};

#define EXT_TABLE_SIZE (sizeof(EXT_TABLE) / sizeof(EXT_TABLE[0]))

/* ── Special filename → Language lookup ──────────────────────────── */

typedef struct {
    const char *filename;
    EngineLanguage language;
} filename_entry_t;

static const filename_entry_t FILENAME_TABLE[] = {
    {"CMakeLists.txt", ENGINE_LANG_CMAKE},
    {"Dockerfile", ENGINE_LANG_DOCKERFILE},
    {"GNUmakefile", ENGINE_LANG_MAKEFILE},
    {"Makefile", ENGINE_LANG_MAKEFILE},
    {"makefile", ENGINE_LANG_MAKEFILE},
    {"meson.build", ENGINE_LANG_MESON},
    {"meson.options", ENGINE_LANG_MESON},
    {"meson_options.txt", ENGINE_LANG_MESON},
    {"kustomization.yaml", ENGINE_LANG_KUSTOMIZE},
    {"kustomization.yml", ENGINE_LANG_KUSTOMIZE},
    /* Note: FILENAME_TABLE uses case-sensitive strcmp, so mixed-case variants
     * (e.g. "Kustomization.yaml") are not matched here.  They fall through to
     * ENGINE_LANG_YAML and are re-classified by engine_is_kustomize_file() in
     * pass_k8s.c, which performs a case-insensitive comparison.  This is the
     * intended behaviour — no additional entries are needed. */
    {".vimrc", ENGINE_LANG_VIMSCRIPT},
    {".zshrc", ENGINE_LANG_ZSH},
    {".zshenv", ENGINE_LANG_ZSH},
    {".zprofile", ENGINE_LANG_ZSH},
    {"BUILD", ENGINE_LANG_STARLARK},
    {"BUILD.bazel", ENGINE_LANG_STARLARK},
    {"WORKSPACE", ENGINE_LANG_STARLARK},
    {"WORKSPACE.bazel", ENGINE_LANG_STARLARK},
    {"requirements.txt", ENGINE_LANG_REQUIREMENTS},
    {"requirements-dev.txt", ENGINE_LANG_REQUIREMENTS},
    {"requirements-test.txt", ENGINE_LANG_REQUIREMENTS},
    {"go.mod", ENGINE_LANG_GOMOD},
    {".env", ENGINE_LANG_DOTENV},
    {".env.local", ENGINE_LANG_DOTENV},

};

#define FILENAME_TABLE_SIZE (sizeof(FILENAME_TABLE) / sizeof(FILENAME_TABLE[0]))

/* ── Language names ──────────────────────────────────────────────── */

static const char *LANG_NAMES[ENGINE_LANG_COUNT] = {
    [ENGINE_LANG_GO] = "Go",
    [ENGINE_LANG_PYTHON] = "Python",
    [ENGINE_LANG_JAVASCRIPT] = "JavaScript",
    [ENGINE_LANG_TYPESCRIPT] = "TypeScript",
    [ENGINE_LANG_TSX] = "TSX",
    [ENGINE_LANG_RUST] = "Rust",
    [ENGINE_LANG_JAVA] = "Java",
    [ENGINE_LANG_CPP] = "C++",
    [ENGINE_LANG_CSHARP] = "C#",
    [ENGINE_LANG_PHP] = "PHP",
    [ENGINE_LANG_LUA] = "Lua",
    [ENGINE_LANG_SCALA] = "Scala",
    [ENGINE_LANG_KOTLIN] = "Kotlin",
    [ENGINE_LANG_RUBY] = "Ruby",
    [ENGINE_LANG_C] = "C",
    [ENGINE_LANG_BASH] = "Bash",
    [ENGINE_LANG_ZIG] = "Zig",
    [ENGINE_LANG_ELIXIR] = "Elixir",
    [ENGINE_LANG_HASKELL] = "Haskell",
    [ENGINE_LANG_OCAML] = "OCaml",
    [ENGINE_LANG_OBJC] = "Objective-C",
    [ENGINE_LANG_SWIFT] = "Swift",
    [ENGINE_LANG_DART] = "Dart",
    [ENGINE_LANG_PERL] = "Perl",
    [ENGINE_LANG_GROOVY] = "Groovy",
    [ENGINE_LANG_ERLANG] = "Erlang",
    [ENGINE_LANG_R] = "R",
    [ENGINE_LANG_HTML] = "HTML",
    [ENGINE_LANG_CSS] = "CSS",
    [ENGINE_LANG_SCSS] = "SCSS",
    [ENGINE_LANG_YAML] = "YAML",
    [ENGINE_LANG_TOML] = "TOML",
    [ENGINE_LANG_HCL] = "HCL",
    [ENGINE_LANG_SQL] = "SQL",
    [ENGINE_LANG_DOCKERFILE] = "Dockerfile",
    [ENGINE_LANG_CLOJURE] = "Clojure",
    [ENGINE_LANG_FSHARP] = "F#",
    [ENGINE_LANG_JULIA] = "Julia",
    [ENGINE_LANG_VIMSCRIPT] = "VimScript",
    [ENGINE_LANG_NIX] = "Nix",
    [ENGINE_LANG_COMMONLISP] = "Common Lisp",
    [ENGINE_LANG_ELM] = "Elm",
    [ENGINE_LANG_FORTRAN] = "Fortran",
    [ENGINE_LANG_CUDA] = "CUDA",
    [ENGINE_LANG_VERILOG] = "Verilog",
    [ENGINE_LANG_EMACSLISP] = "Emacs Lisp",
    [ENGINE_LANG_JSON] = "JSON",
    [ENGINE_LANG_XML] = "XML",
    [ENGINE_LANG_MARKDOWN] = "Markdown",
    [ENGINE_LANG_MAKEFILE] = "Makefile",
    [ENGINE_LANG_CMAKE] = "CMake",
    [ENGINE_LANG_PROTOBUF] = "Protobuf",
    [ENGINE_LANG_GRAPHQL] = "GraphQL",
    [ENGINE_LANG_VUE] = "Vue",
    [ENGINE_LANG_SVELTE] = "Svelte",
    [ENGINE_LANG_MESON] = "Meson",
    [ENGINE_LANG_GLSL] = "GLSL",
    [ENGINE_LANG_INI] = "INI",
    [ENGINE_LANG_MATLAB] = "MATLAB",
    [ENGINE_LANG_KUSTOMIZE] = "Kustomize",
    [ENGINE_LANG_K8S] = "Kubernetes",
    [ENGINE_LANG_SOLIDITY] = "Solidity",
    [ENGINE_LANG_TYPST] = "Typst",
    [ENGINE_LANG_GDSCRIPT] = "GDScript",
    [ENGINE_LANG_GLEAM] = "Gleam",
    [ENGINE_LANG_POWERSHELL] = "PowerShell",
    [ENGINE_LANG_PASCAL] = "Pascal",
    [ENGINE_LANG_DLANG] = "D",
    [ENGINE_LANG_SCHEME] = "Scheme",
    [ENGINE_LANG_FISH] = "Fish",
    [ENGINE_LANG_AWK] = "AWK",
    [ENGINE_LANG_ZSH] = "Zsh",
    [ENGINE_LANG_TCL] = "Tcl",
    [ENGINE_LANG_ADA] = "Ada",
    [ENGINE_LANG_RACKET] = "Racket",
    [ENGINE_LANG_ODIN] = "Odin",
    [ENGINE_LANG_QML] = "QML",
    [ENGINE_LANG_NASM] = "NASM",
    [ENGINE_LANG_ASSEMBLY] = "Assembly",
    [ENGINE_LANG_ASTRO] = "Astro",
    [ENGINE_LANG_BLADE] = "Blade",
    [ENGINE_LANG_GOTEMPLATE] = "Go Template",
    [ENGINE_LANG_LIQUID] = "Liquid",
    [ENGINE_LANG_JINJA2] = "Jinja2",
    [ENGINE_LANG_PRISMA] = "Prisma",
    [ENGINE_LANG_DOTENV] = "DotEnv",
    [ENGINE_LANG_WGSL] = "WGSL",
    [ENGINE_LANG_JSONNET] = "Jsonnet",
    [ENGINE_LANG_PROPERTIES] = "Properties",
    [ENGINE_LANG_STARLARK] = "Starlark",
    [ENGINE_LANG_BICEP] = "Bicep",
    [ENGINE_LANG_REQUIREMENTS] = "Requirements",
    [ENGINE_LANG_HLSL] = "HLSL",
    [ENGINE_LANG_VHDL] = "VHDL",
    [ENGINE_LANG_RST] = "reStructuredText",
    [ENGINE_LANG_MERMAID] = "Mermaid",
    [ENGINE_LANG_PUPPET] = "Puppet",
    [ENGINE_LANG_GITIGNORE] = "gitignore",
    [ENGINE_LANG_LLVM_IR] = "LLVM IR",
    [ENGINE_LANG_GOMOD] = "Go Mod",
    [ENGINE_LANG_APEX] = "Apex",
    [ENGINE_LANG_MOJO] = "Mojo",

};

/* ── Public API ──────────────────────────────────────────────────── */

EngineLanguage engine_language_for_extension(const char *ext) {
    if (!ext || !ext[0]) {
        return ENGINE_LANG_COUNT;
    }

    /* Check user-defined overrides first */
    const engine_userconfig_t *ucfg = engine_get_user_lang_config();
    if (ucfg) {
        EngineLanguage ulang = engine_userconfig_lookup(ucfg, ext);
        if (ulang != ENGINE_LANG_COUNT) {
            return ulang;
        }
    }

    for (size_t i = 0; i < EXT_TABLE_SIZE; i++) {
        if (strcmp(EXT_TABLE[i].ext, ext) == 0) {
            return EXT_TABLE[i].language;
        }
    }
    return ENGINE_LANG_COUNT;
}

EngineLanguage engine_language_for_filename(const char *filename) {
    if (!filename || !filename[0]) {
        return ENGINE_LANG_COUNT;
    }

    /* Check special filenames first */
    for (size_t i = 0; i < FILENAME_TABLE_SIZE; i++) {
        if (strcmp(FILENAME_TABLE[i].filename, filename) == 0) {
            return FILENAME_TABLE[i].language;
        }
    }

    /* DotEnv variant filenames (".env.local", ".env.production", …): the
     * filename starts with ".env." but its last "extension" (e.g. ".local")
     * is not a real language extension.  Match the dotenv convention used by
     * pass_envscan/pass_infrascan (".env" exact, ".env." prefix, "*.env"
     * suffix) so file-index routing agrees with direct extraction. */
    if (strncmp(filename, ".env.", SLEN(".env.")) == 0) {
        return ENGINE_LANG_DOTENV;
    }

    /* Fall back to extension-based lookup.
     * For compound extensions (e.g. ".blade.php") defined in the user config,
     * scan from the first dot in the basename toward the last, checking user
     * config at each position.  Built-in extensions use the last dot only. */
    const char *last_dot = strrchr(filename, '.');
    if (!last_dot) {
        return ENGINE_LANG_COUNT;
    }

    /* Probe compound extensions (e.g. ".blade.php") from the first dot toward
     * the last. Built-in compounds are checked first so e.g. Laravel Blade
     * templates map to Blade rather than the single-extension fallback (PHP);
     * user config can still add more (#258). */
    static const struct {
        const char *ext;
        EngineLanguage lang;
    } COMPOUND_EXT_TABLE[] = {
        {".blade.php", ENGINE_LANG_BLADE},
    };
    const engine_userconfig_t *ucfg = engine_get_user_lang_config();
    const char *p = strchr(filename, '.');
    while (p && p < last_dot) {
        for (size_t i = 0; i < sizeof(COMPOUND_EXT_TABLE) / sizeof(COMPOUND_EXT_TABLE[0]); i++) {
            if (strcmp(p, COMPOUND_EXT_TABLE[i].ext) == 0) {
                return COMPOUND_EXT_TABLE[i].lang;
            }
        }
        if (ucfg) {
            EngineLanguage lang = engine_userconfig_lookup(ucfg, p);
            if (lang != ENGINE_LANG_COUNT) {
                return lang;
            }
        }
        p = strchr(p + SKIP_ONE, '.');
    }

    /* Standard single-extension lookup (built-ins + user overrides). */
    return engine_language_for_extension(last_dot);
}

const char *engine_language_name(EngineLanguage lang) {
    if (lang < 0 || lang >= ENGINE_LANG_COUNT) {
        return "Unknown";
    }
    return LANG_NAMES[lang] ? LANG_NAMES[lang] : "Unknown";
}

/* ── .m file disambiguation ──────────────────────────────────────── */

/* Simple substring search helper */
static bool str_contains(const char *haystack, const char *needle) {
    return strstr(haystack, needle) != NULL;
}

static bool has_objc_markers(const char *buf) {
    return str_contains(buf, "@interface") || str_contains(buf, "@implementation") ||
           str_contains(buf, "@protocol") || str_contains(buf, "@property") ||
           str_contains(buf, "#import") || str_contains(buf, "@selector") ||
           str_contains(buf, "@encode") || str_contains(buf, "@synthesize") ||
           str_contains(buf, "@dynamic");
}

/* Scan lines for MATLAB-specific markers (function/classdef/%%). */
static bool has_matlab_line_markers(const char *buf) {
    const char *line = buf;
    while (*line) {
        const char *p = line;
        while (*p == ' ' || *p == '\t') {
            p++;
        }
        if (strncmp(p, "function ", SLEN("function ")) == 0 ||
            strncmp(p, "function\t", SLEN("function\t")) == 0 ||
            strncmp(p, "classdef ", SLEN("classdef ")) == 0 ||
            strncmp(p, "classdef\t", SLEN("classdef\t")) == 0 || strncmp(p, "%%", PAIR_LEN) == 0 ||
            (*p == '%' && *(p + SKIP_ONE) != '{')) {
            return true;
        }
        const char *nl = strchr(line, '\n');
        if (!nl) {
            break;
        }
        line = nl + SKIP_ONE;
    }
    return false;
}

EngineLanguage engine_disambiguate_m(const char *path) {
    if (!path) {
        return ENGINE_LANG_MATLAB;
    }

    FILE *f = engine_fopen(path, "r");
    if (!f) {
        return ENGINE_LANG_MATLAB;
    }

    /* Read first 4KB */
    char buf[ENGINE_SZ_4K + SKIP_ONE];
    size_t n = fread(buf, SKIP_ONE, ENGINE_SZ_4K, f);
    buf[n] = '\0';
    (void)fclose(f);

    if (has_objc_markers(buf)) {
        return ENGINE_LANG_OBJC;
    }
    if (has_matlab_line_markers(buf)) {
        return ENGINE_LANG_MATLAB;
    }

    return ENGINE_LANG_MATLAB;
}

/* Disambiguate .cls files: .cls is Salesforce Apex. */
EngineLanguage engine_disambiguate_cls(const char *path) {
    (void)path;
    return ENGINE_LANG_APEX;
}

/* Disambiguate .inc files: treat as C include fragment. */
EngineLanguage engine_disambiguate_inc(const char *path) {
    (void)path;
    return ENGINE_LANG_C;
}
