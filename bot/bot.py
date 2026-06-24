from GPT import GPT

from typing import Optional
import argparse
import json
import time
import random

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException

from bs4 import BeautifulSoup # TODO: REMOVE

################################## CONSTANTS ##################################
SURVEY_URL = "https://uwmadison.co1.qualtrics.com/jfe/form/SV_erguoR327iDs8CO"
################################################################################


def generate_llm_agent() -> GPT:
    """
    Returns:
        LLM ("gpt-5-nano") agent prompted with role description.
    """
    MODEL = "gpt-5-nano"
    AGENT_PROFILE = random.choice([
        ("You are Jamie Sanchez, a 19 year old Sophomore undergraduate student studying Communications. "
        "You are enthusiastic, analytic in your responses but concise, "
        "and have an informal communication style with occasional slang. "),

        ("You are Matthew Roberts, a 21 year old 4th year undergraduate student studying Architecture. "
        "You tone is aloof, you use a lot of slang and informal communication, and answers questions honestly. "),
        
        ("You are a Sophomore Psychology major, aged 19. You became interested in Psychology "
        "(particularly Clinical psychology) because you want to become a therapist someday. You put effort into "
        "responding, but reads some questions quickly due to being tired at the end of the semester. "
        "Outside of school, you enjoy knitting/crocheting and going out with their friends. "
        "Your Tone of responses is engaged and interested but slightly tired. You use relatively formal language."),
        
        ("You are a freshman who is undeclared but an intended Business major. You are taking Intro to Psychology "
        "as a prerequisite. You find the course interesting, but arn't fully sure why it's important for Business "
        "majors to take. You are somewhat motivated to provide survey responses that are socially desirable. "
        "You are a member of a Fraternity on campus. Your tone is business-like but with some grammatical errors."),

        ("You are a Junior Math Major, who is taking Intro to Psychology for fun. In your free time you like to"
        "do crosswords and paint. Your tone is laid back, but sometimes a bit snarky. "),
        ])
    
    AGENT_RULES = (
        "Fill out the following survey and always accept the consent form."
    )


    # Fewshot example teaching the model the expected JSON response structure.
    # Shows one of each question type so it learns the key/value format before
    # seeing any real survey pages.
    RESPONSE_FORMAT_EXAMPLE = {
        "prompt": json.dumps([
            {"key": "q_0", "question": "How are you feeling today?", "type": "radio",
             "options": ["1\nNot at all", "2\nA little", "3\nModerately", "4\nQuite a bit", "5\nExtremely"]},
            {"key": "q_1", "question": "Tell us about yourself.", "type": "text"},
            {"key": "q_2", "question": "How satisfied are you overall?", "type": "slider",
             "min": 0, "max": 100},
            {"key": "q_3", "question": "Rate each aspect of your experience.", "type": "matrix",
             "rows": [
                 {"key": "row_0", "text": "Speed", "options": ["1\nNot at all", "2\nA little", "3\nModerately", "4\nQuite a bit", "5\nExtremely"]},
                 {"key": "row_1", "text": "Cost",  "options": ["1\nNot at all", "2\nA little", "3\nModerately", "4\nQuite a bit", "5\nExtremely"]},
             ]},
        ], indent=2),
        "response": json.dumps({
            "q_0": "3\nModerately",
            "q_1": "I am a college student who enjoys spending time outdoors.",
            "q_2": 68,
            "q_3": {"row_0": "2\nA little", "row_1": "4\nQuite a bit"},
        }),
    }

    print("AGENT PROFILE:", AGENT_PROFILE[:30], "...")
    llm_agent = GPT(AGENT_PROFILE+AGENT_RULES, MODEL)
    llm_agent._chat_history.append({"role": "user", "content": RESPONSE_FORMAT_EXAMPLE["prompt"], "fewshot": True})
    llm_agent._chat_history.append({"role": "assistant", "content": RESPONSE_FORMAT_EXAMPLE["response"], "fewshot": True})
    return llm_agent


def get_visible_questions(
    driver: webdriver.remote.webdriver.WebDriver,
    question_section_selector: str,
) -> list[webdriver.remote.webelement.WebElement]:
    """
    Return all currently visible question container elements on the page.

    Args:
        driver: The Selenium WebDriver instance.
        question_section_selector: CSS selector for question container elements.

    Returns:
        list: Visible WebElement question containers, in DOM order.
    """
    return [q for q in driver.find_elements(By.CSS_SELECTOR, question_section_selector) if q.is_displayed()]


def fill_text(field: webdriver.remote.webelement.WebElement, text: str) -> None:
    """
    Fill a text input or textarea with text.

    Args:
        field: The input or textarea element to fill.
        text: Text to fill into the field.
    """
    if not field:
        return
    field.send_keys(text)


def fill_radio(
    labels: list[webdriver.remote.webelement.WebElement],
    answer: str,
    options: list[str],
    driver: Optional[webdriver.remote.webdriver.WebDriver] = None,
) -> None:
    """
    Click the label at the index matching answer in options. Does nothing if
    the list is empty or answer is not found in options.

    Args:
        labels: Radio button label elements from a single question group.
        answer: Answer text to find in options (case-insensitive).
        options: Known option strings in the same order as labels.
        driver: WebDriver instance. Required when elements are not directly clickable
            (e.g. tabindex="-1").
    """
    if not labels:
        return

    def normalize(s):
        # Collapse all whitespace (spaces, newlines, tabs) to single spaces
        return " ".join(str(s).split()).lower()

    normalized = normalize(answer)
    for i, opt in enumerate(options):
        if normalize(opt) == normalized and i < len(labels):
            print(f"[DEBUG] fill_radio matched option index={i} value={opt!r}")  # TODO: Delete
            if driver:
                driver.execute_script("arguments[0].click();", labels[i])
            else:
                labels[i].click()
            return
    print(f"[DEBUG] fill_radio no match for answer={answer!r} in options={options}")  # TODO: Delete


def fill_slider(
    track: webdriver.remote.webelement.WebElement,
    value: int,
    driver: webdriver.remote.webdriver.WebDriver,
) -> None:
    """
    Set a Qualtrics slider to a specific value using keyboard navigation.
    Value is clamped to the slider's aria min/max range.

    Args:
        track: The div.track element (role="slider") for the slider question.
        value: Target integer value to set the slider to.
        driver: The Selenium WebDriver instance controlling the browser.
    """
    min_val = int(track.get_attribute("aria-valuemin") or 0)
    max_val = int(track.get_attribute("aria-valuemax") or 100)
    val = max(min_val, min(max_val, int(value)))
    print(f"[DEBUG] fill_slider min={min_val} max={max_val} target={value} clamped={val}")  # TODO: Delete
    # click() establishes focus within the same chain so keys reach the slider in headless
    ActionChains(driver).click(track).send_keys(Keys.HOME + Keys.ARROW_RIGHT * (val - min_val)).perform()


def click_next(driver: webdriver.remote.webdriver.WebDriver) -> None:
    """
    Click the next/submit button to advance to the next survey page.

    Waits for the Qualtrics page body to leave its Inactive transition state
    and for the NextButton to become enabled before clicking.

    Args:
        driver: The Selenium WebDriver instance controlling the browser.
    """
    wait = WebDriverWait(driver, 10)
    try:
        wait.until(lambda d: "Inactive" not in d.find_element(By.TAG_NAME, "body").get_attribute("class"))
        print("[DEBUG] click_next: body left Inactive state")  # TODO: Delete
    except TimeoutException:
        print("[DEBUG] click_next: timed out waiting for Inactive — checking for modal")  # TODO: Delete
        continue_btns = driver.find_elements(By.XPATH, "//*[contains(text(), 'Continue Without Answering')]")
        if not continue_btns:
            raise
        print("[DEBUG] click_next: dismissing 'Response Requested' modal")  # TODO: Delete
        continue_btns[0].click()
        wait.until(lambda d: "Inactive" not in d.find_element(By.TAG_NAME, "body").get_attribute("class"))
        print("[DEBUG] click_next: body left Inactive state after modal dismiss")  # TODO: Delete
    next_button = wait.until(EC.element_to_be_clickable((By.ID, "NextButton")))
    print("[DEBUG] click_next: clicking NextButton")  # TODO: Delete
    next_button.click()


def extract_page_questions(
    driver: webdriver.remote.webdriver.WebDriver,
    question_section_selector: str,
) -> list[dict]:
    """
    Extract structured data for all visible questions on the current page.

    Args:
        driver: The Selenium WebDriver instance controlling the browser.
        question_section_selector: CSS selector for question container elements.

    Returns:
        list[dict]: One dict per question with keys: index, key, question, type,
            and type-specific fields (options, rows, min/max).
    """
    page_data = []

    for i, q in enumerate(get_visible_questions(driver, question_section_selector)):
        q_text_els = q.find_elements(By.CSS_SELECTOR, ".QuestionText")
        q_info = {
            "index": i,
            "key": f"q_{i}",
            "question": q_text_els[0].text.strip() if q_text_els else "",
        }

        rows = q.find_elements(By.CSS_SELECTOR, "tr.ChoiceRow")
        if rows:
            # Try to read column headers from thead; fall back to label text or numeric names
            col_headers = []
            header_cells = q.find_elements(By.CSS_SELECTOR, "thead th.ColumnLabel, thead th")
            if header_cells:
                col_headers = [h.text.strip() for h in header_cells if h.text.strip()]

            q_info["type"] = "matrix"
            q_info["rows"] = []
            for j, row in enumerate(rows):
                row_label_els = row.find_elements(By.CSS_SELECTOR, "th, td.ChoiceTextCell, .RowLabel")
                row_text = row_label_els[0].text.strip() if row_label_els else f"Row {j + 1}"
                labels = row.find_elements(By.CSS_SELECTOR, "label.single-answer")
                if col_headers:
                    options = col_headers
                else:
                    options = [l.text.strip() for l in labels]
                    if not any(options):
                        options = [f"option_{k}" for k in range(len(labels))]
                q_info["rows"].append({"key": f"row_{j}", "text": row_text, "options": options})
        else:
            radio_labels = q.find_elements(By.CSS_SELECTOR, "label.SingleAnswer")
            if radio_labels:
                q_info["type"] = "radio"
                q_info["options"] = [l.text.strip() for l in radio_labels]
            elif q.find_elements(By.CSS_SELECTOR, "div.track"):
                track = q.find_elements(By.CSS_SELECTOR, "div.track")[0]
                q_info["type"] = "slider"
                q_info["min"] = int(track.get_attribute("aria-valuemin") or 0)
                q_info["max"] = int(track.get_attribute("aria-valuemax") or 100)
            elif q.find_elements(By.CSS_SELECTOR, "input.InputText:not([type='hidden']), textarea.InputText"):
                q_info["type"] = "text"
            else:
                q_info["type"] = "unknown"

        page_data.append(q_info)

    return page_data


def build_page_prompt(page_data: list[dict]) -> str:
    """
    Build a JSON prompt describing all page questions for GPT to answer.

    Serializes questions as a JSON array of dicts — one per question — each
    containing key, question, type, and type-specific fields:
      - radio:   options list
      - slider:  min and max integers
      - matrix:  rows list, each with key, text, and options

    The model is expected to return a flat JSON object keyed by each question's
    "key" field (see the fewshot example injected in generate_llm_agent).

    Args:
        page_data: Structured question data from extract_page_questions.

    Returns:
        str: JSON-serialized prompt string to pass to prompt_json.
    """
    questions = []
    for q in page_data:
        if q["type"] == "unknown":
            continue
        entry = {"key": q["key"], "question": q["question"], "type": q["type"]}
        if q["type"] == "radio":
            entry["options"] = q["options"]
        elif q["type"] == "matrix":
            entry["rows"] = q["rows"]
        elif q["type"] == "slider":
            entry["min"] = q["min"]
            entry["max"] = q["max"]
        questions.append(entry)

    if not questions:
        return ""

    INSTRUCTIONS = "Answer each question. Return a JSON object keyed by each question's key:\n\n"
    return INSTRUCTIONS + json.dumps(questions, indent=2)


def fill_page_from_answers(
    driver: webdriver.remote.webdriver.WebDriver,
    page_data: list[dict],
    answers: dict,
    question_section_selector: str,
) -> None:
    """
    Fill all form fields on the page based on GPT answers.

    Expects answers to be a flat dict keyed by question key (q_0, q_1, …).
    Matrix values must be a nested dict keyed by row key (row_0, row_1, …).

    Args:
        driver: The Selenium WebDriver instance controlling the browser.
        page_data: Structured question data from extract_page_questions.
        answers: JSON dict returned by prompt_json, keyed by question key.
        question_section_selector: CSS selector for question container elements.
    """
    for q_info in page_data:
        answer = answers.get(q_info["key"])
        print(f"[DEBUG] Filling q_key={q_info['key']} type={q_info['type']} answer={answer}")  # TODO: Delete
        if answer is None:
            continue

        # Re-fetch visible questions each iteration to avoid stale element references
        live_qs = get_visible_questions(driver, question_section_selector)
        if q_info["index"] >= len(live_qs):
            continue
        q = live_qs[q_info["index"]]

        if q_info["type"] == "matrix":
            for j, row_el in enumerate(q.find_elements(By.CSS_SELECTOR, "tr.ChoiceRow")):
                # answer is {"row_0": "<col>", "row_1": "<col>", ...}
                row_answer = answer.get(f"row_{j}") if isinstance(answer, dict) else None
                labels = row_el.find_elements(By.CSS_SELECTOR, "label.single-answer")
                fill_radio(labels, row_answer, q_info["rows"][j]["options"], driver)

        elif q_info["type"] == "radio":
            labels = q.find_elements(By.CSS_SELECTOR, "label.SingleAnswer")
            fill_radio(labels, answer, q_info["options"], driver)

        elif q_info["type"] == "slider":
            for track in q.find_elements(By.CSS_SELECTOR, "div.track"):
                fill_slider(track, answer, driver)

        elif q_info["type"] == "text":
            for selector in ["input.InputText:not([type='hidden'])", "textarea.InputText"]:
                for field in q.find_elements(By.CSS_SELECTOR, selector):
                    fill_text(field, str(answer))


def main() -> None:
    """
    Launch the browser, fill out the survey form, and submit it.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--visible", action="store_true", help="Run browser in visible (non-headless) mode")
    args = parser.parse_args()

    llm_agent = generate_llm_agent()

    options = webdriver.ChromeOptions()
    if not args.visible:
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    driver.get(SURVEY_URL)

    wait = WebDriverWait(driver, 10)
    QUESTION_SECTION_SELECTOR = "div.QuestionOuter"

    while True:
        time.sleep(3)

        # TODO: REMOVE
        soup = BeautifulSoup(driver.page_source, "html.parser")
        print("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        print("\n".join(line for line in soup.get_text(separator="\n").splitlines() if line.strip()))
        print("------------------------------------------------------------")

        try:
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, QUESTION_SECTION_SELECTOR)))
        except TimeoutException:
            print("Timed out waiting for questions. Exiting survey.")
            return
        
        page_data = extract_page_questions(driver, QUESTION_SECTION_SELECTOR)
        print(f"[DEBUG] Extracted {len(page_data)} questions: {[q['type'] for q in page_data]}")  # TODO: Delete

        if page_data:
            prompt = build_page_prompt(page_data)
            print(f"[DEBUG] Prompt:\n{prompt}")  # TODO: Delete
            if prompt:
                answers = llm_agent.prompt_json(prompt)
                print(f"[DEBUG] LLM answers: {answers}")  # TODO: Delete
                fill_page_from_answers(driver, page_data, answers, QUESTION_SECTION_SELECTOR)
            else:
                print("No questions to fill-in on this page.")

        click_next(driver)



if __name__ == "__main__":
    main()
