from abc import ABC, abstractmethod
from playwright.sync_api import sync_playwright
import os

class BaseWebAPI(ABC):
    """
    Базовый класс для всех Web API моделей.
    Инкапсулирует логику запуска браузера, маскировки и управления ресурсами.
    """
    def __init__(self, profile_dir: str, url: str, headless: bool = True, disable_images: bool = True):
        self.profile_dir = profile_dir
        self.url = url
        self.headless = headless
        self.browser = None
        self.playwright = None
        
        os.makedirs(profile_dir, exist_ok=True)
        
        try:
            self.playwright = sync_playwright().start()
            
            args =[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars"
            ]
            
            if disable_images:
                args.append("--blink-settings=imagesEnabled=false")
                
            self.browser = self.playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=headless,
                channel="chrome",
                ignore_default_args=["--enable-automation"],
                args=args,
                viewport={'width': 1280, 'height': 800},
                permissions=["clipboard-read", "clipboard-write"]
            )
            self.page = self.browser.new_page()
            
            # Скрываем свойство webdriver
            self.page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.page.goto(self.url, wait_until="domcontentloaded")
            self.wait_for_ready()
        except Exception as e:
            self.close()
            raise e

    @abstractmethod
    def wait_for_ready(self, **kwargs):
        """Ожидание загрузки интерфейса чата (например, поля ввода)"""
        pass

    @abstractmethod
    def ask(self, prompt: str, files: list = None, **kwargs) -> str:
        """Отправка промпта и получение ответа"""
        pass

    def close(self):
        """Обязательное закрытие браузера"""
        if getattr(self, 'browser', None):
            try:
                self.browser.close()
            except Exception:
                pass
        if getattr(self, 'playwright', None):
            try:
                self.playwright.stop()
            except Exception:
                pass
import time
import re


def _clean_text(text: str) -> str:
    """Очищает текст, но сохраняет отступы (важно для кода)."""
    return re.sub(r'\n{3,}', '\n\n', text).strip()

class DeepSeekAPI(BaseWebAPI):
    def __init__(self, profile_name="default", headless=True, expert_mode=True, deep_think=True, timeout=600, stable_count=7):
        self.expert_mode = expert_mode
        self.deep_think_default = deep_think
        self.timeout = timeout
        self.stable_count = stable_count
        super().__init__(
            profile_dir=f"./profiles/deepseek_{profile_name}",
            url="https://chat.deepseek.com/",
            headless=headless,
            # Для прохождения Cloudflare / Turnstile часто требуются картинки и canvas
            disable_images=False 
        )

    def wait_for_ready(self, disable_expert=False):
        self._handle_cloudflare()
        # Ожидаем появления поля ввода. 
        self.page.wait_for_selector("textarea, #chat-input", timeout=30000)

        # Устанавливаем режим (Expert или Instant)
        try:
            if self.expert_mode and not disable_expert:
                btn = self.page.locator('div[data-model-type="expert"]')
            else:
                btn = self.page.locator('div[data-model-type="default"]')
                
            btn.wait_for(state="visible", timeout=5000)
            if btn.count() > 0:
                btn.click()
                time.sleep(0.5)
        except Exception as e:
            print(f"Не удалось переключить режим модели: {e}")
    def _handle_cloudflare(self):
        """
        Попытка автоматического обхода проверки Cloudflare.
        Если появляется Turnstile, иногда достаточно кликнуть по нему.
        """
        time.sleep(3)
        try:
            for frame in self.page.frames:
                if "cloudflare" in frame.url or "turnstile" in frame.url:
                    print("Обнаружен Cloudflare, пытаюсь пройти проверку...")
                    box = frame.locator("input[type='checkbox'], .cb-c, body")
                    if box.count() > 0:
                        box.first.click()
                        time.sleep(5)
        except Exception as e:
            print(f"Ошибка при прохождении Cloudflare: {e}")


    def new_chat(self, disable_expert=False):
        print("Создание нового чата...")
        try:
            new_btn = self.page.locator('div, a').filter(has_text="New chat").first
            if new_btn.is_visible():
                new_btn.click(timeout=2000)
                time.sleep(1.5)
            else:
                self.page.goto(self.url, wait_until="domcontentloaded")
        except:
            self.page.goto(self.url, wait_until="domcontentloaded")
        self.wait_for_ready(disable_expert=disable_expert)
    def ask(self, prompt: str, files: list = None, deep_think: bool = None, _is_retry: bool = False, cancel_event=None, **kwargs) -> str:
        # Очищаем буфер перед отправкой
        self.page.evaluate("navigator.clipboard.writeText('').catch(() => {})")

        # Переключение DeepThink
        use_deep_think = deep_think if deep_think is not None else self.deep_think_default
        try:
            # Улучшенный локатор: ищем именно кнопки-переключатели (.ds-toggle-button)
            dt_btn = self.page.locator('.ds-toggle-button:has-text("DeepThink"), .ds-toggle-button:has-text("Глубокое")').first
            try:
                # Ожидаем появления кнопки до 5 секунд (быстрый таймаут)
                dt_btn.wait_for(state="visible", timeout=5000)
            except:
                pass # Таймаут игнорируем, проверим видимость ниже
            
            if dt_btn.is_visible():
                class_attr = dt_btn.get_attribute('class') or ""
                is_selected = 'ds-toggle-button--selected' in class_attr
                if use_deep_think and not is_selected:
                    dt_btn.click(timeout=5000, force=True)
                    time.sleep(0.5)
                elif not use_deep_think and is_selected:
                    dt_btn.click(timeout=5000, force=True)
                    time.sleep(0.5)
            else:
                print("Кнопка DeepThink не найдена. Продолжаю без неё.")
        except Exception as e:
            print(f"Ошибка при переключении DeepThink (игнорирую): {e}")

        if files:
            try:
                file_input = self.page.locator('input[type="file"]')
                file_input.set_input_files(files)
                time.sleep(1.5)  # Даем время на появление индикатора загрузки в UI
                # Ждем окончания загрузки файлов
                loading_texts =[
                    "обработка", "Uploading", "Parsing", "processing", 
                    "В ожидании", "Загрузка"
                ]
                for text in loading_texts:
                    try:
                        for el in self.page.get_by_text(text).all():
                            if el.is_visible():
                                el.wait_for(state="hidden", timeout=30000)
                    except:
                        pass
                time.sleep(2)
            except Exception as e:
                print(f"Не удалось прикрепить файлы: {e}")

        md_selector = ".ds-markdown, .markdown-body, div[class*='markdown'], div[class*='prose']"
        
        # Запоминаем состояние до отправки (чтобы отличить новый ответ от старого)
        try:
            initial_md_count = self.page.locator(md_selector).count()
            initial_texts = self.page.locator(md_selector).all_inner_texts()
            initial_last_text = initial_texts[-1].strip() if initial_texts else ""
        except:
            initial_md_count = 0
            initial_last_text = ""

        chat_input = self.page.locator("textarea, #chat-input").first
        chat_input.fill(prompt)
        time.sleep(0.5)

        # Улучшенная логика отправки с проверкой очистки поля ввода
        send_success = False
        for attempt in range(4):
            chat_input.press("Enter")
            time.sleep(1.5)
            
            val = chat_input.input_value()
            if not val or val.strip() == "":
                send_success = True
                break
                
            # Если Enter не сработал, пробуем нажать кнопку отправки (иконка SVG)
            try:
                send_btn = self.page.locator('div[role="button"]:has(svg)').last
                if send_btn.is_visible():
                    send_btn.click(timeout=1000, force=True)
                time.sleep(1.5)
                val = chat_input.input_value()
                if not val or val.strip() == "":
                    send_success = True
                    break
            except:
                pass

        if not send_success:
            if not _is_retry:
                print("Не удалось отправить запрос (поле не очистилось). Создаю новый чат...")
                self.new_chat()
                return self.ask(prompt, files=files, deep_think=deep_think, _is_retry=True)
            elif self.expert_mode and not getattr(self, '_expert_disabled_temp', False):
                print("Снова не удалось отправить. Отключаю Expert mode и создаю новый чат...")
                self.new_chat(disable_expert=True)
                self._expert_disabled_temp = True
                res = self.ask(prompt, files=files, deep_think=deep_think, _is_retry=True)
                self._expert_disabled_temp = False
                return res
            else:
                return "__ERROR_PROMPT_TOO_LARGE__"

        last_text = ""
        stable_count = 0
        max_wait_sec = self.timeout
        stable_count_target = self.stable_count
        timeout_occurred = False

        # JS-скрипт для поиска и нажатия кнопки копирования ТОЛЬКО под последним сообщением.
        # Он ищет панель действий (группу из 2+ кнопок ds-icon-button), которая появляется
        # после текста только тогда, когда генерация полностью завершена.
        js_find_and_click = """
        () => {
            const mds = document.querySelectorAll('.ds-markdown, .markdown-body, div[class*="markdown"], div[class*="prose"]');
            if (mds.length === 0) return false;
            const lastMd = mds[mds.length - 1];
            
            let curr = lastMd;
            // Идем вверх по дереву на несколько уровней
            for (let i = 0; i < 5; i++) {
                if (!curr) break;
                
                // Ищем среди всех соседей, идущих строго ПОСЛЕ текущего узла
                let sibling = curr.nextElementSibling;
                while (sibling) {
                    // Исключаем панель ввода, чтобы случайно не нажать на скрепку (открытие файла)
                    const isInputBlock = (sibling.matches && sibling.matches('textarea, #chat-input, form, [contenteditable="true"]')) || 
                                         (sibling.querySelector && sibling.querySelector('textarea, #chat-input, form, [contenteditable="true"]'));
                    if (isInputBlock) {
                        sibling = sibling.nextElementSibling;
                        continue;
                    }

                    // Панель кнопок (Copy, Like, Dislike)
                    const btns = sibling.querySelectorAll('div.ds-icon-button[role="button"], button[aria-label*="Copy"], div[aria-label*="Copy"]');
                    if (btns.length > 0) {
                        btns[0].click(); // Первая кнопка обычно Copy
                        return true;
                    }
                    sibling = sibling.nextElementSibling;
                }
                curr = curr.parentElement;
            }
            return false;
        }
        """

        for _ in range(max_wait_sec):
            if cancel_event and cancel_event.is_set():
                return "__ERROR_CANCELLED__"
            time.sleep(1)
            
            try:
                current_md_count = self.page.locator(md_selector).count()
                texts = self.page.locator(md_selector).all_inner_texts()
                texts =[t.strip() for t in texts if t.strip()]
                # Очищаем курсоры в конце, чтобы они не сбрасывали счетчик стабильности
                current_text = texts[-1].rstrip(" |▌_") if texts else ""
            except:
                current_md_count = 0
                current_text = ""

            # Проверяем, начал ли появляться новый ответ
            has_new_message = False
            if current_md_count > initial_md_count:
                has_new_message = True
            elif current_text and current_text != initial_last_text:
                has_new_message = True

            if has_new_message:
                # 1. ОСНОВНОЙ ТРИГГЕР: Пытаемся найти и нажать кнопку копирования
                clicked = self.page.evaluate(js_find_and_click)
                if clicked:
                    time.sleep(0.5) # Ждем полсекунды, чтобы текст точно попал в буфер
                    clip_val = self.page.evaluate("navigator.clipboard.readText().catch(() => '')")
                    print("Ответ промта:",clip_val,"Конец ответа промта")
                    if clip_val:
                        return clip_val
                
                # 2. РЕЗЕРВНЫЙ ТРИГГЕР: стабильность текста
                if current_text and current_text == last_text:
                    stable_count += 1
                else:
                    stable_count = 0

                last_text = current_text

                if stable_count >= stable_count_target:
                    break
        else:
            timeout_occurred = True

        if timeout_occurred:
            if not _is_retry:
                print("Превышено время ожидания (10 минут). Создаем новый чат...")
                self.new_chat()
                return self.ask(prompt, files=files, deep_think=deep_think, _is_retry=True)
            elif self.expert_mode and not getattr(self, '_expert_disabled_temp', False):
                print("Снова таймаут. Отключаю Expert mode и создаю новый чат...")
                self.new_chat(disable_expert=True)
                self._expert_disabled_temp = True
                res = self.ask(prompt, files=files, deep_think=deep_think, _is_retry=True)
                self._expert_disabled_temp = False
                return res
            else:
                return "__ERROR_PROMPT_TOO_LARGE__"

        # ФОЛЛБЕК НА ТЕКСТ СО СТРАНИЦЫ (Без форматирования Markdown)
        if last_text:
            return _clean_text(last_text)
        else:
            return "Не удалось найти ответ в DOM. Возможно, изменилась верстка."
import time
import re


def _clean_text(text: str) -> str:
    """Очищает текст, но сохраняет отступы (важно для кода)."""
    return re.sub(r'\n{3,}', '\n\n', text).strip()

class GeminiAPI(BaseWebAPI):
    def __init__(self, profile_name="default", headless=True, timeout=600):
        self.timeout = timeout
        super().__init__(
            profile_dir=f"./profiles/gemini_{profile_name}",
            url="https://aistudio.google.com/app/prompts/new_chat",
            headless=headless,
            disable_images=True
        )

    def wait_for_ready(self, **kwargs):
        self.page.wait_for_selector("textarea, [contenteditable='true']", timeout=15000)


    def new_chat(self):
        print("Создание нового чата Gemini...")
        try:
            self.page.goto(self.url, wait_until="domcontentloaded")
            self.wait_for_ready()
        except:
            pass
    def ask(self, prompt: str, files: list = None, _is_retry: bool = False, cancel_event=None, **kwargs) -> str:
        self.page.evaluate("navigator.clipboard.writeText('').catch(() => {})")

        if files:
            try:
                self.page.locator('[data-test-id="add-media-button"], button[aria-label*="Insert"]').first.click()
                file_input = self.page.locator('input[type="file"]')
                file_input.wait_for(state="attached", timeout=5000)
                file_input.set_input_files(files)
                
                time.sleep(1.5)  # Даем время на появление индикатора
                # Ждем пока исчезнет надпись Loading
                loading_texts =["Loading", "В ожидании", "Загрузка", "Uploading"]
                for text in loading_texts:
                    try:
                        for el in self.page.get_by_text(text).all():
                            if el.is_visible():
                                el.wait_for(state="hidden", timeout=30000)
                    except:
                        pass
                time.sleep(1)
            except Exception as e:
                print(f"Не удалось прикрепить файлы: {e}")

        try:
            initial_thumb_count = self.page.locator('button[aria-label="Good response"], .turn-footer button, button:has(.material-symbols-outlined:has-text("thumb_up"))').count()
        except:
            initial_thumb_count = 0

        # Скрываем возможные открытые overlay-меню (например, менюшку после загрузки файла)
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(300)

        chat_input = self.page.locator("textarea,[contenteditable='true'], [role='textbox']").first
        chat_input.click(force=True)
        chat_input.fill(prompt)
        self.page.wait_for_timeout(500)

        chat_input.press("Control+Enter")

        max_wait_sec = self.timeout
        start_time = time.time()
        completed = False

        while time.time() - start_time < max_wait_sec:
            if cancel_event and cancel_event.is_set():
                return "__ERROR_CANCELLED__"
            try:
                current_thumb_count = self.page.locator('button[aria-label="Good response"], .turn-footer button, button:has(.material-symbols-outlined:has-text("thumb_up"))').count()
                if current_thumb_count > initial_thumb_count:
                    completed = True
                    break
            except:
                pass
            self.page.wait_for_timeout(1000)

        if not completed:
            if not _is_retry:
                print("Превышено время ожидания (10 минут). Создаем новый чат...")
                self.new_chat()
                return self.ask(prompt, files=files, _is_retry=True, **kwargs)
            else:
                return "__ERROR_PROMPT_TOO_LARGE__"

        self.page.wait_for_timeout(1000) # Даем UI немного времени на финальный рендеринг

        try:
            last_turn = self.page.locator('ms-chat-turn, div[data-turn-role="Model"], div.chat-turn-container.model').last
            
            # Попытка 1: найти кнопку меню и скопировать как Markdown
            copy_success = False
            try:
                options_btn = last_turn.locator('button[aria-label="Open options"], button:has(.material-symbols-outlined:has-text("more_vert"))').last
                if options_btn.count() > 0 and options_btn.is_visible():
                    options_btn.click(timeout=3000, force=True)
                    self.page.wait_for_timeout(500)
                    
                    copy_btn = self.page.locator('button[role="menuitem"]:has-text("Copy as markdown"), button[role="menuitem"]:has-text("Copy")').first
                    if copy_btn.count() > 0 and copy_btn.is_visible():
                        copy_btn.click(timeout=3000, force=True)
                        self.page.wait_for_timeout(1000)
                        copy_success = True
            except:
                pass

            if copy_success:
                clip_val = self.page.evaluate("navigator.clipboard.readText().catch(() => '')")
                if clip_val:
                    return clip_val
            
            # Попытка 2: Читаем текст прямо из DOM (фоллбек на случай изменений UI)
            try:
                last_turn.evaluate("""(el) => {
                    const footers = el.querySelectorAll('.turn-footer, .actions-container');
                    footers.forEach(f => f.style.display = 'none');
                }""")
            except:
                pass
                
            text = last_turn.inner_text()
            if text.strip():
                return _clean_text(text)
                
        except Exception as e:
            return f"Ошибка при извлечении текста: {e}"

        return "Не удалось получить текст ответа."
import sys
import argparse
import os


class MajorchicAPIAdapter:
    """
    Адаптер для Majorchic API, повторяющий интерфейс BomjAPI.
    """
    def __init__(self, backend="deepseek", headless=False, profile_name="default", expert_mode=True, deep_think=True, timeout=600, stable_count=7):
        self.backend = backend
        self.headless = headless
        self.profile_name = profile_name
        self.expert_mode = expert_mode
        self.deep_think = deep_think
        self.timeout = timeout
        self.stable_count = stable_count
        self.ai = None

    def _init_ai(self):
        if self.ai is None:
            if self.backend == "gemini":
                self.ai = GeminiAPI(profile_name=self.profile_name, headless=self.headless, timeout=self.timeout)
            else:
                self.ai = DeepSeekAPI(
                    profile_name=self.profile_name, 
                    headless=self.headless,
                    expert_mode=self.expert_mode,
                    deep_think=self.deep_think,
                    timeout=self.timeout,
                    stable_count=self.stable_count
                )

    def _parse_payload(self, payload):
        if isinstance(payload, str):
            return payload
        if "messages" in payload:
            parts = []
            for msg in payload["messages"]:
                role = msg.get("role", "Unknown")
                content = msg.get("content", "")
                parts.append(f"{role}:\n{content}")
            return "\n\n".join(parts)
        if "promt" in payload:
            return payload["promt"]
        if "prompt" in payload:
            return payload["prompt"]
        return "Empty prompt"

    def send(self, payload, cancel_event=None):
        self._init_ai()
        prompt = self._parse_payload(payload)
        
        if self.backend == "deepseek":
            dt = payload.get("deep_think", self.deep_think) if isinstance(payload, dict) else self.deep_think
            ot = self.ai.ask(prompt, deep_think=dt, cancel_event=cancel_event)
            print("Ответ от мажёрчик API:", ot, "Конец ответа мажёрчик API")
            return ot
        else:
            ot = self.ai.ask(prompt, cancel_event=cancel_event)
            print("Ответ от мажёрчик API:", ot, "Конец ответа мажёрчик API")
            return ot

    def close(self):
        if self.ai:
            self.ai.close()
            self.ai = None

def main():
    parser = argparse.ArgumentParser(description="Запуск AI моделей (Gemini или DeepSeek) с интерактивной консолью.")
    parser.add_argument("model", nargs="?", choices=["gemini", "deepseek"], help="Модель для использования (если не указана, будет запрошена в консоли)")
    parser.add_argument("--headless", action="store_true", help="Запустить браузер в фоновом режиме (без графического интерфейса)")
    parser.add_argument("--files", nargs="*", help="Пути к файлам для прикрепления (будут отправлены с первым промптом)")
    parser.add_argument("--profile", type=str, default="default", help="Имя профиля для использования (по умолчанию: default)")
    parser.add_argument("--no-expert", action="store_true", help="Отключить режим Expert (для DeepSeek)")
    parser.add_argument("--no-deepthink", action="store_true", help="Отключить DeepThink (для DeepSeek)")
    args = parser.parse_args()

    # Определение модели
    model_choice = args.model
    if not model_choice:
        print("Доступные модели:")
        print("1. Gemini (Google AI Studio)")
        print("2. DeepSeek (chat.deepseek.com)")
        choice = input("\nВыберите модель (1/2): ").strip()
        if choice == "1":
            model_choice = "gemini"
        elif choice == "2":
            model_choice = "deepseek"
        else:
            print("Неверный выбор.")
            sys.exit(1)

    # Инициализация
    ai = None
    try:
        if model_choice == "gemini":
            print(f"\nИнициализация Gemini (профиль: {args.profile})...")
            ai = GeminiAPI(profile_name=args.profile, headless=args.headless)
        else:
            print(f"\nИнициализация DeepSeek (профиль: {args.profile})...")
            ai = DeepSeekAPI(profile_name=args.profile, headless=args.headless, expert_mode=not args.no_expert, deep_think=not args.no_deepthink)

        print("Браузер готов. Вводите промпты (для выхода введите 'exit' или 'quit').")
        print("-" * 50)

        current_files = [os.path.abspath(f) for f in args.files] if args.files else None

        while True:
            prompt = input("\nПромпт: ").strip()
            if prompt.lower() in ("exit", "quit"):
                print("Завершение работы.")
                break
            if not prompt:
                print("Промпт не может быть пустым.")
                continue

            print("\n[Ответ]:")
            response = ai.ask(prompt, files=current_files)
            print(response)
            current_files = None  # Сбрасываем файлы после первой отправки

    except KeyboardInterrupt:
        print("\n\nПрерывание пользователя.")
    except Exception as e:
        print(f"\nПроизошла ошибка: {e}")
    finally:
        if ai:
            ai.close()


if __name__ == "__main__":
    main()
