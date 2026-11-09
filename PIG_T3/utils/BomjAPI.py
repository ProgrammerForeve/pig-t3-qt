import tkinter as tk
from tkinter import messagebox
import pickle
import os


class BomjAPI:
    """
    BomjAPI is a utility class for manual testing and mocking of LLM API responses.
    It provides a Tkinter-based GUI to manually input, paste, and validate responses for given prompts.

    Example:
        >>> def length_validator(text):
        ...     return len(text) > 10
        ...
        >>> api = BomjAPI(validators={"GPT-4": length_validator})
        >>> response = api.send({
        ...     "model": "GPT-4", 
        ...     "prompt": "Tell me a story"
        ... })
        >>> print(response)
    """

    def __init__(self, validators=None):
        """
        Initializes the BomjAPI instance.

        :param validators: A single validation function applied to all models, or a dictionary
                           mapping model names to specific validation functions.
                           A validation function must take a string (response) and return a boolean.
        :type validators: callable or dict, optional
        """
        self.validators = validators
        self.data = {}  # Format: {prompt: response}
        self.last_response = ""  # To check for duplicate consecutive responses

    def _get_validator(self, model_name):
        """
        Retrieves the appropriate validation function for a given model name.

        :param model_name: The name of the model to get the validator for.
        :type model_name: str
        :return: The validation function if found, otherwise None.
        :rtype: callable or None
        """
        if callable(self.validators):
            return self.validators
        elif isinstance(self.validators, dict):
            return self.validators.get(model_name)
        return None

    def _parse_payload(self, payload):
        """
        Parses the incoming payload dictionary into a single formatted string prompt.
        Handles both 'messages' list format and simple 'prompt'/'promt' string format.

        :param payload: The request payload containing the prompt or messages.
        :type payload: dict
        :return: A formatted string representing the complete prompt.
        :rtype: str
        """
        # Handle 'messages' format (e.g., OpenAI API style)
        if "messages" in payload:
            parts = []
            for msg in payload["messages"]:
                role = msg.get("role", "Unknown")
                content = msg.get("content", "")
                parts.append(f"{role}:\n{content}")
            return "\n\n".join(parts)

        # Handle 'prompt' or 'promt' (typo fallback) format
        if "promt" in payload:
            return payload["promt"]
        if "prompt" in payload:
            return payload["prompt"]

        return "Empty prompt"

    def send(self, payload, parent=None):
        """
        Sends a request to the GUI, opening a window for manual response input.
        This method blocks execution until the user submits a response via the GUI.

        :param payload: A dictionary containing the request details (model, prompt, etc.)
                        or a simple string representing the prompt.
        :type payload: dict or str
        :param parent: Optional parent Tkinter window. If provided, uses Toplevel.
        :return: The user-provided response text.
        :rtype: str

        Example:
            >>> api = BomjAPI()
            >>> result = api.send("What is the capital of France?")
        """
        if isinstance(payload, str):
            payload = {
                "model": "Standard",
                "promt": payload,
            }

        model = payload.get("model", "Unknown_Model")
        prompt_text = self._parse_payload(payload)
        validator = self._get_validator(model)

        # Variable to store the GUI result
        self._current_result = None

        if parent is not None:
            root = tk.Toplevel(parent)
            root.transient(parent)
            root.grab_set()
        else:
            root = tk.Tk()
        root.title(f"Request to {model}")
        
        # Configure window size and center it on the screen
        window_width = 800
        window_height = 500
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        center_x = int(screen_width / 2 - window_width / 2)
        center_y = int(screen_height / 2 - window_height / 2)
        root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

        # Grid configuration to ensure strictly equal sized halves
        root.grid_columnconfigure(0, weight=1, uniform="half")
        root.grid_columnconfigure(1, weight=1, uniform="half")
        root.grid_rowconfigure(0, weight=1)

        # --- Left Frame (Prompt Display) ---
        left_frame = tk.Frame(root, padx=10, pady=10)
        left_frame.grid(row=0, column=0, sticky="nsew")

        tk.Label(left_frame, text="PROMPT TEXT (ТУТ ТЕКСТ ПРОМПТА)").pack(anchor="w")

        prompt_text_widget = tk.Text(left_frame, wrap=tk.WORD, bg="#f0f0f0")
        prompt_text_widget.insert("1.0", prompt_text)
        prompt_text_widget.config(state=tk.DISABLED)  # Make it read-only
        prompt_text_widget.pack(fill=tk.BOTH, expand=True, pady=5)

        def copy_to_clipboard():
            root.clipboard_clear()
            root.clipboard_append(prompt_text)
            messagebox.showinfo("Copied", "Prompt copied to clipboard!")

        tk.Button(left_frame, text="COPY (СКОПИРОВАТЬ)", command=copy_to_clipboard).pack(anchor="w")

        # --- Right Frame (Response Input) ---
        right_frame = tk.Frame(root, padx=10, pady=10)
        right_frame.grid(row=0, column=1, sticky="nsew")

        tk.Label(right_frame, text="RESPONSE TEXT (ТУТ ТЕКСТ ОТВЕТА)").pack(anchor="w")

        response_text_widget = tk.Text(right_frame, wrap=tk.WORD)
        response_text_widget.pack(fill=tk.BOTH, expand=True, pady=5)
        response_text_widget.focus_set()

        # Frame for buttons below the response text area
        buttons_frame = tk.Frame(right_frame)
        buttons_frame.pack(fill=tk.X)

        def paste_from_clipboard():
            try:
                clipboard_data = root.clipboard_get()
                response_text_widget.insert(tk.INSERT, clipboard_data)
            except tk.TclError:
                pass  # Clipboard is empty or contains non-text data

        # Hotkeys for pasting (Ctrl+V for English layout, Ctrl+M for Russian 'V' key)
        root.bind('<Control-v>', lambda e: paste_from_clipboard())
        root.bind('<Control-V>', lambda e: paste_from_clipboard())
        root.bind('<Control-m>', lambda e: paste_from_clipboard())
        root.bind('<Control-M>', lambda e: paste_from_clipboard())

        def check_validation():
            if not validator:
                return True
            current_text = response_text_widget.get("1.0", tk.END).strip()
            is_valid = validator(current_text)

            if is_valid:
                check_btn.config(bg="lightgreen")
                return True
            else:
                check_btn.config(bg="salmon")
                messagebox.showwarning("Validation Failed", "The response did not pass validation!")
                return False

        def submit_response():
            current_text = response_text_widget.get("1.0", tk.END).strip()

            # 1. Check for duplicate response compared to the previous one
            if current_text == self.last_response and current_text != "":
                if not messagebox.askyesno("Duplicate Match",
                                           "This response is exactly the same as the previous one.\nAre you sure you want to proceed?"):
                    return

            # 2. Pre-submit validation check
            if validator:
                is_valid = validator(current_text)
                if not is_valid:
                    if not messagebox.askyesno("Warning",
                                               "The response does not meet the criteria (validation failed).\nProceed anyway?"):
                        return
                    if not messagebox.askyesno("Are you sure?",
                                               "Are you absolutely sure you want to submit an invalid response?"):
                        return

            # Save the data and close the GUI
            self._current_result = current_text
            self.last_response = current_text
            self.data[prompt_text] = current_text
            if parent is None:
                root.quit()
            root.destroy()

        def on_closing():
            if parent is None:
                root.quit()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_closing)
        # "Check" button (only visible if a validator exists)
        if validator:
            check_btn = tk.Button(buttons_frame, text="CHECK (ПРОВЕРИТЬ)", command=check_validation)
            check_btn.pack(side=tk.TOP, anchor="e", pady=(0, 5))

        # "Paste" and "Accept/Submit" buttons
        tk.Button(buttons_frame, text="PASTE (ВСТАВИТЬ)", command=paste_from_clipboard).pack(side=tk.LEFT)
        tk.Button(buttons_frame, text="▶ ACCEPT (ПРИНЯТЬ)", command=submit_response, bg="lightblue").pack(side=tk.RIGHT)

        # Start the main GUI loop (blocks until the window is destroyed)
        if parent is not None:
            parent.wait_window(root)
        else:
            root.mainloop()

        return self._current_result
    def get_data(self):
        """
        Returns the accumulated prompt-response history.

        :return: A dictionary mapping prompts to their corresponding responses.
        :rtype: dict
        
        Example:
            >>> api.get_data()
            {'Tell me a joke': 'Why did the chicken cross the road?...'}
        """
        return self.data

    def save(self, filepath="bomj_data.pkl"):
        """
        Saves the accumulated prompt-response data to a pickle file.

        :param filepath: The path to the file where data should be saved.
                         Defaults to 'bomj_data.pkl'.
        :type filepath: str
        """
        with open(filepath, 'wb') as f:
            pickle.dump(self.data, f)
        print(f"Data successfully saved to {filepath}")

    def load(self, filepath="bomj_data.pkl"):
        """
        Loads prompt-response data from a pickle file.

        :param filepath: The path to the file to load data from.
                         Defaults to 'bomj_data.pkl'.
        :type filepath: str
        """
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                self.data = pickle.load(f)
            print(f"Data successfully loaded from {filepath}")
        else:
            print(f"File {filepath} not found.")
