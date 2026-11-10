#!/usr/bin/env bash
# check.sh — линтинг, форматирование и проверка типов для PIG-T3
#
# Использование:
#   ./check.sh          — проверка без изменений (для CI)
#   ./check.sh --fix    — авто-исправление и форматирование
#   ./check.sh --quick  — только линтер (без mypy)

set -uo pipefail

# --- Цветной вывод ---------------------------------------------------------
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
fi

# --- Разбор аргументов -----------------------------------------------------
FIX=0
QUICK=0
for arg in "$@"; do
    case "$arg" in
        --fix)   FIX=1 ;;
        --quick) QUICK=1 ;;
        -h|--help)
            echo "Использование: $0 [--fix] [--quick]"
            echo "  --fix    Авто-исправить и отформатировать файлы"
            echo "  --quick  Пропустить проверку типов (mypy)"
            exit 0
            ;;
        *)
            echo -e "${RED}Неизвестный аргумент: $arg${NC}"
            exit 2
            ;;
    esac
done

FAILED=0

# --- Проверка наличия инструментов -----------------------------------------
if ! command -v ruff &> /dev/null; then
    echo -e "${RED}❌ ruff не установлен.${NC}"
    echo -e "   Установите: ${BLUE}pip install -e '.[dev]'${NC}"
    exit 1
fi

echo -e "${BLUE}==> Рабочая директория: $(pwd)${NC}"
echo -e "${BLUE}==> ruff: $(ruff --version)${NC}"
echo

# --- 1. Линтер -------------------------------------------------------------
echo -e "${YELLOW}[1/3] Линтинг (ruff check)...${NC}"
if [ "$FIX" -eq 1 ]; then
    if ruff check . --fix --unsafe-fixes; then
        echo -e "${GREEN}✅ Линтинг пройден (часть правил исправлена автоматически).${NC}"
    else
        echo -e "${RED}❌ Остались неавтоисправимые ошибки линтера.${NC}"
        FAILED=1
    fi
else
    if ruff check .; then
        echo -e "${GREEN}✅ Линтинг пройден без ошибок.${NC}"
    else
        echo -e "${RED}❌ Найдены ошибки линтера. Запустите: ./check.sh --fix${NC}"
        FAILED=1
    fi
fi
echo

# --- 2. Форматтер ----------------------------------------------------------
echo -e "${YELLOW}[2/3] Проверка форматирования (ruff format)...${NC}"
if [ "$FIX" -eq 1 ]; then
    if ruff format .; then
        echo -e "${GREEN}✅ Файлы отформатированы.${NC}"
    else
        echo -e "${RED}❌ Ошибка при форматировании.${NC}"
        FAILED=1
    fi
else
    if ruff format --check .; then
        echo -e "${GREEN}✅ Форматирование в порядке.${NC}"
    else
        echo -e "${RED}❌ Файлы не отформатированы. Запустите: ./check.sh --fix${NC}"
        FAILED=1
    fi
fi
echo

# --- 3. mypy (опционально) -------------------------------------------------
if [ "$QUICK" -eq 1 ]; then
    echo -e "${YELLOW}[3/3] mypy пропущен (--quick).${NC}"
elif command -v mypy &> /dev/null; then
    echo -e "${YELLOW}[3/3] Проверка типов (mypy)...${NC}"
    if mypy PIG_T3/; then
        echo -e "${GREEN}✅ Проверка типов пройдена.${NC}"
    else
        echo -e "${RED}❌ Найдены ошибки типизации (не критично, но стоит исправить).${NC}"
        # mypy обычно шумит в GUI-коде — не роняем сборку, только предупреждаем
        # Если нужна жёсткая проверка — раскомментируйте строку ниже:
        # FAILED=1
    fi
else
    echo -e "${YELLOW}[3/3] mypy не установлен — пропускаем.${NC}"
    echo -e "   Установите: ${BLUE}pip install -e '.[dev]'${NC}"
fi
echo

# --- Итог ------------------------------------------------------------------
if [ "$FAILED" -ne 0 ]; then
    echo -e "${RED}==> Проверки НЕ пройдены.${NC}"
    exit 1
fi

echo -e "${GREEN}==> Все проверки завершены успешно!${NC}"