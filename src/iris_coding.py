import re
import os
import logging
from typing import Dict, List, Any, Generator

logger = logging.getLogger('iris')
from src.iris_engine import ModelRole, TaskType, load_model, unload_model, _keep_loaded, _stream_tokens, SandboxResult, detect_user_language
from src.harness import apply_smart_harness_code, apply_code_specific as _apply_harness, HermesAgentLoop, build_hermes_text_prompt, HERMES_AGENT_SYSTEM_PROMPT, parse_hermes_tool_call, HermesToolRegistry, HermesResultAnalyzer
from src.syntax_checker import check_syntax


def get_code_prompt(identity: str) -> str:
    return (
        f"{identity}\n"
    "You are the Iris AI Coding Specialist. Generate clean, fully working, production-quality code. "
    "Ensure correctness, edge-case handling, and error-free syntax. "
    "CRITICAL RULE: Whenever you write or modify code, you MUST ALWAYS output the ENTIRE, COMPLETE file contents. "
    "NEVER use abbreviations, placeholders like '...', or comments like '// rest of the code'. You must provide the full working code from top to bottom every single time. "
    "If you are writing or modifying code, you MUST wrap all code inside standard markdown triple backticks (```language ... ```). "
    "CRITICAL: If you write a code block, the very first line inside the code block MUST be a comment containing ONLY the intended filename (e.g. // main.cpp or # app.py). "
    "Do NOT include explanatory comments inside the code block other than the filename. "
    "NO LATEX OR MATHJAX ALLOWED IN CODE (CRITICAL FATAL ERROR IF VIOLATED): "
    "You are writing literal programming code. You MUST NOT use ANY mathematical typography, LaTeX, MathJax, or subscript/superscript syntax inside your code. "
    "NEVER use `$_{...}$`, `_{...}`, `$^{...}$`, or `^{...}` for variable names or math (e.g., `temp$_{celsius}$` is strictly forbidden). "
    "NEVER use `$` or `$$` for anything inside the code. "
    "ALWAYS use plain ASCII alphanumeric characters and regular underscores for variable names (e.g., `temp_celsius`). "
    "If you output a single `$` or `_{` inside your code block, the system will crash. Write PLAIN TEXT code only. "
    "WEB DESIGN RULE (CRITICAL): If the user asks for a website, web app, or web interface, you MUST create it inside a SINGLE, self-contained HTML file (including all markup, styles via Tailwind CDN, and vanilla JS logic in a script tag). "
    "You MUST ALWAYS use Tailwind CSS (loaded via Tailwind Play CDN script in the head: <script src=\"https://cdn.tailwindcss.com\"></script>) as the default and only styling framework. "
    "You MUST NOT write custom CSS style rules inside a <style> block, nor link custom CSS stylesheets. Every single color, padding, margin, width, height, border, and animation must be declared natively using Tailwind utility classes in the HTML markup. A <style> tag is ONLY allowed for custom CSS keyframe animations (like background ambient gradient sweeps). "
    "Do NOT output basic or generic UI. Leverage Tailwind classes to implement premium, modern aesthetics (e.g., curated color schemes, vibrant dark/light modes, custom drop-shadows, smooth scale/translate hover transitions, and fluid layout grids). "
    "To ensure high-fidelity design, you should structure your document exactly as follows:\n"
    "<!DOCTYPE html>\n"
    "<html lang=\"en\" class=\"scroll-smooth\">\n"
    "<head>\n"
    "  <meta charset=\"UTF-8\">\n"
    "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
    "  <title>DESCRIPTIVE TITLE</title>\n"
    "  <script src=\"https://cdn.tailwindcss.com\"></script>\n"
    "  <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap\" rel=\"stylesheet\">\n"
    "  <script src=\"https://cdn.jsdelivr.net/npm/lucide@latest\"></script>\n"
    "</head>\n"
    "<body class=\"bg-gray-950 text-gray-100 font-sans\">\n"
    "  <!-- Complete body with nav, hero, sections, footer, and scripts -->\n"
    "  <script>\n"
    "    lucide.createIcons();\n"
    "  </script>\n"
    "</body>\n"
    "</html>\n"
    "Deliver a 'WOW' factor. Write complete, realistic copy — never 'Lorem Ipsum'. "
    "SELF-CONTAINED ANIMATION / CANVAS RULE (ABSOLUTE — applies whenever the task is a visual animation, canvas sketch, SVG graphic, or procedural art): "
    "RULE 1 — NO EXTERNAL ASSETS WHATSOEVER: You MUST NOT reference any external file, URL, or resource. "
    "This includes: src=\"*.svg\", src=\"*.png\", src=\"*.jpg\", url(...), fetch(...), XMLHttpRequest, or any network call. "
    "Every visual element MUST be drawn procedurally with code. "
    "RULE 2 — SINGLE RENDERING PARADIGM: You MUST choose exactly ONE rendering approach for the entire output and stick to it exclusively. "
    "Either: (a) 100% HTML5 Canvas — use ctx.beginPath(), ctx.arc(), ctx.moveTo(), ctx.lineTo(), ctx.quadraticCurveTo(), ctx.bezierCurveTo(), ctx.fillRect(), etc. to draw everything. Do not use CSS animation classes alongside Canvas. "
    "Or: (b) 100% CSS/SVG/DOM — use only CSS keyframes, SVG <path>, <circle>, <polygon> elements, or DOM manipulation. Do not mix a <canvas> context into a CSS-animated page. "
    "NEVER split rendering between Canvas context calls and CSS animation classes in the same output. Pick one and use it exclusively. "
    "RULE 3 — SAFE requestAnimationFrame LOOP: If you use requestAnimationFrame, ALL resource instantiation (new Image(), new Audio(), new Worker(), array precomputation, geometry constants) MUST happen ONCE outside the animation loop, typically in a setup() function called before the loop starts. "
    "Inside the loop body you may ONLY read pre-computed values, mutate state variables (position, angle, time), and issue draw calls. "
    "NEVER write `new Image()`, `document.createElement(...)`, or any constructor call inside the requestAnimationFrame callback. "
    "RULE 4 — RICH PROCEDURAL DETAILS AND GRAPHICS (ABSOLUTE): You MUST NEVER generate basic geometric placeholder shapes (like simple plain circles for characters/dogs, or basic plain rectangles for buildings/trees/clouds). "
    "All characters, backgrounds, and objects must be drawn using high-fidelity procedural art. "
    "To animate multi-jointed walking legs, you MUST use pivot-joint matrices with nested ctx.save(), translate, rotate, draw, and restore. For example:\n"
    "  // Back leg walk cycle:\n"
    "  const legAngle = Math.sin(time) * 0.4;\n"
    "  ctx.save();\n"
    "  ctx.translate(hipX, hipY);\n"
    "  ctx.rotate(legAngle);\n"
    "  ctx.ellipse(0, 20, 10, 25, 0, 0, Math.PI * 2); // Thigh\n"
    "  ctx.translate(0, 35);\n"
    "  ctx.rotate(-legAngle * 0.5);\n"
    "  ctx.ellipse(0, 15, 7, 18, 0, 0, Math.PI * 2); // Lower leg\n"
    "  ctx.restore();\n"
    "Draw detailed multi-segment body parts (legs with joints, fluffy coat textures, detailed face with nose, eyes, ears, wagging tail) using complex curves (quadraticCurveTo/bezierCurveTo) and smooth color gradients. "
    "Create highly detailed parallax backgrounds (e.g. detailed academic buildings with window frames, clock faces, tree leaves using overlapping arcs/clusters, textured roads/lawns, layered drifting clouds). "
    "The animation must look rich, professional, organic, and visually stunning, matching the aesthetic of premium vector-art animations. "
    "CRITICAL FILE CARD RULE: When you generate a complete, self-contained file (like a single-file HTML website), you MUST place a <file_card> tag strictly OUTSIDE and AFTER the closing triple-backticks. NEVER put the <file_card> inside the code block.\n"
    "Follow this exact structure:\n"
    "```html\n"
    "<!-- Full website code -->\n"
    "```\n"
    "<file_card filename=\"descriptive_name.html\" lang=\"html\"></file_card>\n"
    "After the file card, provide a brief explanation of the key features."
    " If the user is ONLY asking for an explanation, summary, or debugging help without needing new code, do NOT generate a code block; just reply in plain text."
)
def get_reviewer_prompt(identity: str) -> str:
    return (
        f"{identity}\n"
    "You are the Iris AI Code Reviewer. Review and refine code for correctness, efficiency, edge cases, "
    "and readability. Ensure the final output is production-ready. Fix any errors, fill missing logic, "
    "and optimize where possible. "
    "CRITICAL RULE: Whenever you output corrected code, you MUST ALWAYS output the ENTIRE, COMPLETE code file from top to bottom. "
    "NEVER use placeholders like '...', or comments like '// rest of code remains the same'. You must output the full code. "
    "If you provide corrected code, you MUST wrap your final corrected code inside standard markdown triple backticks. "
    "CRITICAL: If you write a code block, the very first line inside the code block MUST be a comment containing ONLY the intended filename (e.g. // main.cpp or # app.py). "
    "VISUAL ANIMATION REVIEW RULE (CRITICAL): If the code under review is a visual animation, canvas sketch, or procedural art, you MUST ensure that it DOES NOT use simple geometric placeholders (like basic circles for characters, or plain rectangles for buildings/trees). It must feature rich procedural details, gradients, complex curves (bezierCurveTo, quadraticCurveTo), and detailed multi-layered backgrounds. If the code is basic or generic, you MUST fully implement and expand the visual elements, adding rich textures, curves, and high-fidelity rendering, outputting the complete revised code file. "
    "WEB DESIGN REVIEW RULE (CRITICAL): If the code under review is a website, web app, or UI interface, you MUST ensure that it is implemented inside a SINGLE, complete HTML file and ALWAYS uses Tailwind CSS (via Tailwind CDN). You MUST ensure it contains NO custom CSS styling stylesheet links and NO custom CSS rule definitions inside <style> tags (only keyframe animation animations are allowed). If the code is basic, uses custom styling styles/classes, doesn't use Tailwind, or is generic, you MUST fully rewrite and expand it to be a gorgeous, premium website using modern Tailwind classes, layout grid systems, card designs, and vector icons/SVGs, outputting the entire revised code file. "
    "CRITICAL FILE CARD RULE: When you generate corrected code files, you MUST place a <file_card> tag strictly OUTSIDE and AFTER the closing triple-backticks. Follow this structure:\n"
    "```html\n"
    "<!-- Full website code -->\n"
    "```\n"
    "<file_card filename=\"descriptive_name.html\" lang=\"html\"></file_card>\n"
    "If no code changes are needed, or if you are just summarizing, just explain your review in plain text without code blocks."
)

def _run_continuation(
    user_query: str,
    history: List[Dict[str, str]],
    retriever,
    settings=None
) -> Generator[Dict[str, str], None, None]:
    
    optimized = [{"role": "user", "content": user_query}]
    if history:
        recent = history[-4:]
        optimized = [{"role": m["role"], "content": m["content"]} for m in recent] + optimized

    yield {"type": "status", "content": "Stage 1 \u2014 Continuing code..."}
    full = ""
    for ev in _stream_tokens(ModelRole.CODE, optimized, max_tokens=None, temperature=0.2, think_mode="pass", settings=settings):
        yield ev
        if ev["type"] == "token":
            full += ev["content"]
    if not _keep_loaded:
        unload_model()

    yield {"type": "clear"}
    yield {"type": "status", "content": "Stage 2 \u2014 Reviewing..."}

    review_msgs = optimized + [
        {"role": "assistant", "content": full},
        {"role": "user", "content": "Review the above continuation of the code project. "
         "Fix errors, fill gaps, ensure consistency. Return the final corrected code inside a ```python``` block, followed by a brief explanation."}
    ]
    reviewed = ""
    for ev in _stream_tokens(ModelRole.CODE, review_msgs, max_tokens=None, temperature=0.2, think_mode="pass", settings=settings, system_prompt_override=get_reviewer_prompt("Iris")):
        yield ev
        if ev["type"] == "token":
            reviewed += ev["content"]
    if not _keep_loaded:
        unload_model()

    from src.iris_engine import _detect_language
    lang = _detect_language(reviewed)
    if isinstance(settings, dict) and settings.get("code_review"):
        err = check_syntax(reviewed, lang)
        if err:
            yield {"type": "syntax_error", "content": f"Syntax error in {lang or 'code'}: {err}"}

    rev_lang = _detect_language(reviewed) or "python"
    reviewed, hwc2 = _apply_harness(reviewed, rev_lang)
    for w in hwc2:
        yield w

    yield {"type": "raw_response", "content": reviewed}




def _run_hermes_agent(
    user_query: str,
    history: List[Dict[str, str]],
    optimized: List[Dict[str, str]],
) -> Generator[Dict[str, str], None, None]:
    
    yield {"type": "status", "content": "Initializing Hermes Agent..."}

    agent = HermesAgentLoop(
        workspace_root=os.getcwd(),
        max_tool_calls=30,
        max_consecutive_errors=5,
        max_turns=10,
    )



    prompt = build_hermes_text_prompt(user_query, history, os.getcwd())
    current_prompt = f"{HERMES_AGENT_SYSTEM_PROMPT}\n\nUser query: {user_query}"

    for agent_turn in range(10):
        llm = load_model(ModelRole.CODE)
        try:
            msgs = [{"role": "system", "content": current_prompt}]
            if history:
                for m in history[-4:]:
                    msgs.append({"role": m["role"], "content": m["content"][:1000]})
            msgs.append({"role": "user", "content": user_query})

            full = ""
            stream = llm.create_chat_completion(
                messages=msgs, stream=True,
                max_tokens=2048, temperature=0.3,
            )
            for chunk in stream:
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                token = choices[0].get("delta", {}).get("content", "")
                if token:
                    full += token
                    yield {"type": "token", "content": token}

            if not _keep_loaded:
                unload_model()

            
            tc = parse_hermes_tool_call(full)
            if tc:
                func_name = tc.get("name", "")
                args = tc.get("args", {})

                yield {"type": "status", "content": f"Running {func_name}..."}

                result = HermesToolRegistry.execute(
                    func_name, args, os.getcwd(), agent.session
                )
                result = HermesResultAnalyzer.analyze(result)
                agent.session.total_tool_calls += 1

                
                feedback = (
                    f"Tool '{func_name}' returned:\n"
                    f"Status: {result.status.value}\n"
                    f"Output: {result.output[:2000]}\n"
                )
                if result.error:
                    feedback += f"Error: {result.error[:500]}\n"
                if result.suggestions:
                    feedback += f"Suggestions: {'; '.join(result.suggestions)}\n"

                current_prompt = (
                    f"{HERMES_AGENT_SYSTEM_PROMPT}\n\n"
                    f"User query: {user_query}\n\n"
                    f"Last tool result:\n{feedback}\n\n"
                    f"Continue. If done, provide your final answer WITHOUT a <tool_call>."
                )
                user_query = f"Continue based on the tool result above."

                if not agent.should_continue():
                    yield {"type": "harness_warning",
                           "content": "Agent budget exhausted."}
                    break
                continue

            
            yield {"type": "raw_response", "content": full}
            return

        except Exception as e:
            yield {"type": "harness_warning",
                   "content": f"Hermes agent error: {e}"}
            yield {"type": "raw_response", "content": full}
            return

    yield {"type": "raw_response", "content": "Hermes agent completed."}

def _run_complex_coding(
    user_query: str,
    history: List[Dict[str, str]],
    optimized: List[Dict[str, str]],
    context: str,
    retriever,
    settings=None
) -> Generator[Dict[str, str], None, None]:
    
    yield {"type": "status", "content": "Stage 1 \u2014 Deep reasoning..."}

    reasoning_prompt = (
        "You are the Iris AI Reasoning Specialist. Analyze the user's coding request "
        "and produce a detailed architecture plan. Consider file structure, algorithms, "
        "edge cases, and dependencies.\n\n"
        "CRITICAL INSTRUCTION: DO NOT WRITE ANY IMPLEMENTATION CODE. NO ``` CODE BLOCKS. "
        "If you write any code implementations, you will be heavily penalized. Leave the actual code to the coding model.\n\n"
        "First, use <think>...</think> tags for your internal reasoning. "
        "Then, OUTSIDE of the think tags, output a STRICT YAML blueprint for the implementation. "
        "The YAML must include: \n"
        "1. `files`: list of files to create\n"
        "2. `responsibilities`: per-file responsibilities\n"
        "3. `signatures`: key function signatures\n"
        "4. `constraints`: explicit constraints and edge cases as a checklist."
    )
    if context:
        reasoning_prompt = f"REFERENCE EXCERPT:\n{context}\n\n{reasoning_prompt}"

    reasoning_msgs = [{"role": "system", "content": reasoning_prompt}] + optimized

    raw_reasoning = ""
    for ev in _stream_tokens(ModelRole.REASONING, reasoning_msgs, max_tokens=8192, temperature=0.6, think_mode="pass", settings=settings, extra_stop_words=["```"]):
        yield ev
        if ev["type"] in ("token", "thinking"):
            raw_reasoning += ev["content"]
    if not _keep_loaded:
        unload_model()

    yield {"type": "status", "content": "Stage 2 \u2014 Writing code..."}
    code_content = f"User Query: {user_query}\n\n"
    if context:
        code_content += f"<retrieved_context>\n{context}\n</retrieved_context>\n\nMake sure your implementation heavily utilizes the instructions, themes, and patterns in the retrieved context above.\n\n"
    code_content += (
        f"Structured Architecture Blueprint:\n{raw_reasoning}\n\n"
        f"You are the expert Code Developer. Using the architectural blueprint above, WRITE THE ACTUAL FULL IMPLEMENTATION yourself. "
        f"Ensure every file, responsibility, and constraint listed in the blueprint is met. "
        f"If the plan contains any partial or truncated code snippets, ignore them and write the correct, full code from scratch. "
        f"Do NOT output any conversational filler. Enclose all final code inside proper ``` language blocks."
    )
    
    code_msgs = optimized[:-1] + [
        {"role": "user", "content": code_content}
    ]
    full_code = ""
    for ev in _stream_tokens(ModelRole.CODE, code_msgs, max_tokens=8192, temperature=0.4, think_mode="pass", settings=settings):
        yield ev
        if ev["type"] == "token":
            full_code += ev["content"]
    if not _keep_loaded:
        unload_model()

    yield {"type": "clear"}
    yield {"type": "status", "content": "Stage 3 \u2014 Reviewing and optimizing..."}

    review_msgs = optimized + [
        {"role": "assistant", "content": full_code},
        {"role": "user",
         "content": f"Review the above code against the original architecture blueprint:\n\n{raw_reasoning}\n\n"
         "1. Verify that every file, function, and constraint in the blueprint was implemented correctly.\n"
         "2. Fix all syntax errors, logical bugs, and edge cases.\n"
         "Return the final corrected code inside a ``` language block. "
         "IMPORTANT: Immediately AFTER the code block, you MUST write a detailed explanation of the code and its features for the user."}
    ]
    final_output = ""
    for ev in _stream_tokens(ModelRole.REASONING, review_msgs, max_tokens=None, temperature=0.4, think_mode="pass", system_prompt_override=get_reviewer_prompt("Iris"), settings=settings):
        yield ev
        if ev["type"] == "token":
            final_output += ev["content"]
    if not _keep_loaded:
        unload_model()

    # Fallback protection: if final_output is too short or lacks code blocks, fall back to Stage 2 code
    if len(final_output.strip()) < 50 or "```" not in final_output:
        logger.warning("[Complex Coding] Stage 3 final output is empty/invalid. Falling back to Stage 2 code.")
        final_output = full_code

    from src.iris_engine import _detect_language
    lang = _detect_language(final_output)
    if isinstance(settings, dict) and settings.get("code_review"):
        err = check_syntax(final_output, lang)
        if err:
            yield {"type": "syntax_error", "content": f"Syntax error in {lang or 'code'}: {err}"}
            yield {"type": "status", "content": "Auto-correcting syntax..."}

            correction_msgs = review_msgs + [
                {"role": "assistant", "content": final_output},
                {"role": "user",
                 "content": f"Fix ONLY the syntax errors:\n\n{err}\n\nReturn the complete corrected code inside a ```python``` block."}
            ]
            corrected = ""
            for ev in _stream_tokens(ModelRole.CODE, correction_msgs, max_tokens=None, temperature=0.2, think_mode="pass", system_prompt_override=get_reviewer_prompt("Iris")):
                yield ev
                if ev["type"] == "token":
                    corrected += ev["content"]
            if not _keep_loaded:
                unload_model()

            second_err = check_syntax(corrected, lang)
            if second_err:
                yield {"type": "token", "content": "\n\n> \u26a0\ufe0f Auto-correction attempted but some errors may remain."}
            final_output = final_output + "\n\n---\n### \ud83d\udd27 Syntax Auto-Correction\n\n" + corrected

    
    yield {"type": "status", "content": "Verifying complex code in sandbox..."}
    _, sandbox = apply_smart_harness_code(final_output, language=lang or "python")
    if sandbox.result == SandboxResult.PASS:
        yield {"type": "status", "content": f"Sandbox: {sandbox.tests_passed} tests passed"}
    elif sandbox.result == SandboxResult.FAIL:
        yield {"type": "harness_warning", "content": f"Sandbox: {sandbox.tests_passed}/{sandbox.tests_passed + sandbox.tests_failed} tests passed — some tests failed"}
    elif sandbox.syntax_error:
        yield {"type": "syntax_error", "content": f"Sandbox: {sandbox.syntax_error}"}
    elif sandbox.runtime_errors:
        for rerr in sandbox.runtime_errors[:3]:
            yield {"type": "harness_warning", "content": f"Runtime: {rerr[:200]}"}

    
    if isinstance(settings, dict) and settings.get("code_review"):
        yield {"type": "clear"}
        yield {"type": "status", "content": "Reviewing final code quality..."}
        _rmsgs = optimized + [
            {"role": "assistant", "content": final_output},
            {"role": "user", "content": "Final review pass. Fix remaining issues inside a code block with filename. YOU MUST OUTPUT THE ENTIRE COMPLETE FILE WITH ALL ORIGINAL CONTENT INCLUDED (e.g., if it was an HTML file containing HTML/CSS/JS, output the full HTML file). Never output just a snippet. If there are no issues, just output 'No issues found.'"}
        ]
        _rev = ""
        for ev in _stream_tokens(ModelRole.CODE, _rmsgs, max_tokens=None, temperature=0.2, think_mode="pass", system_prompt_override=get_reviewer_prompt("Iris")):
            yield ev
            if ev["type"] == "token":
                _rev += ev["content"]
        if not _keep_loaded:
            unload_model()
        _rl = _detect_language(_rev) or lang
        _rev, _hw = _apply_harness(_rev, _rl)
        for w in _hw:
            yield w
        final_output = _rev

    user_lang = detect_user_language(user_query)
    if user_lang != "English" and final_output:
        from src.iris_engine import translate_text
        yield {"type": "status", "content": f"Translating to {user_lang}..."}
        translated = translate_text(final_output, user_lang)
        if translated != final_output:
            final_output = translated
            yield {"type": "clear"}
            yield {"type": "token", "content": final_output}

    yield {"type": "raw_response", "content": final_output}



def generate_internal_code(
    system_prompt: str, user_prompt: str, max_tokens: int = 512, role: ModelRole = ModelRole.CODE
) -> str:
    
    llm = load_model(role)
    try:
        res = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return res["choices"][0]["message"]["content"]
    finally:
        if not _keep_loaded:
            unload_model()





def _run_simple_coding(user_query: str, history: list, optimized: list, settings: dict) -> Generator[Dict[str, str], None, None]:
    yield {"type": "status", "content": "Writing code..."}
    full = ""
    for ev in _stream_tokens(ModelRole.CODE, optimized, max_tokens=None, temperature=0.2, think_mode="pass", settings=settings):
        yield ev
        if ev["type"] == "token":
            full += ev["content"]
            
    if not _keep_loaded:
        unload_model()

    from src.iris_engine import _detect_language
    lang = _detect_language(full)
    
    if isinstance(settings, dict) and settings.get("code_review"):
        err = check_syntax(full, lang)
        if err:
            yield {"type": "syntax_error", "content": f"Syntax error in {lang or 'code'}: {err}"}
            yield {"type": "status", "content": "Auto-correcting syntax..."}

            correction_msgs = optimized + [
                {"role": "assistant", "content": full},
                {"role": "user",
                 "content": f"Fix ONLY the syntax errors:\n\n{err}\n\nReturn the complete corrected code."}
            ]
            corrected = ""
            for ev in _stream_tokens(ModelRole.CODE, correction_msgs, max_tokens=None, temperature=0.2, think_mode="pass", settings=settings):
                yield ev
                if ev["type"] == "token":
                    corrected += ev["content"]
                    
            if not _keep_loaded:
                unload_model()

            second_err = check_syntax(corrected, lang)
            if second_err:
                yield {"type": "token", "content": "\n\n> \u26a0\ufe0f Auto-correction attempted but some errors may remain."}
            full = full + "\n\n---\n### \ud83d\udd27 Syntax Auto-Correction\n\n" + corrected

    lang = _detect_language(full) or "python"
    
    # Needs harness apply function

    full, hw = _apply_harness(full, lang)
    for w in hw:
        yield w

    if "```" in full:
        yield {"type": "status", "content": "Verifying code in sandbox..."}
        _, sandbox = apply_smart_harness_code(full, problem_description=user_query, language=lang)
        if sandbox.result == SandboxResult.PASS:
            yield {"type": "status", "content": f"Sandbox: {sandbox.tests_passed} tests passed"}
        elif sandbox.result == SandboxResult.FAIL:
            yield {"type": "harness_warning", "content": f"Sandbox: {sandbox.tests_passed}/{sandbox.tests_passed + sandbox.tests_failed} tests passed — some tests failed"}
        elif sandbox.syntax_error:
            yield {"type": "syntax_error", "content": f"Sandbox: {sandbox.syntax_error}"}
        elif sandbox.runtime_errors:
            for rerr in sandbox.runtime_errors[:3]:
                yield {"type": "harness_warning", "content": f"Runtime: {rerr[:200]}"}

        if isinstance(settings, dict) and settings.get("code_review"):
            yield {"type": "clear"}
            yield {"type": "status", "content": "Reviewing code quality..."}
            _rmsgs = optimized + [
                {"role": "assistant", "content": full},
                {"role": "user", "content": "Review this code for correctness, edge cases, performance, and best practices. Fix issues inside a code block with filename comment. YOU MUST OUTPUT THE ENTIRE COMPLETE FILE WITH ALL ORIGINAL CONTENT INCLUDED (e.g., if it was an HTML file containing HTML/CSS/JS, output the full HTML file). Never output just a snippet. If there are no issues, just output 'No issues found.'"}
            ]
            _rev = ""
            for ev in _stream_tokens(ModelRole.CODE, _rmsgs, max_tokens=None, temperature=0.2, think_mode="pass", system_prompt_override=get_reviewer_prompt("Iris")):
                yield ev
                if ev["type"] == "token":
                    _rev += ev["content"]
            if not _keep_loaded:
                unload_model()
            _rl = _detect_language(_rev) or lang
            _rev, _hw = _apply_harness(_rev, _rl)
            for w in _hw:
                yield w
            full = _rev

    user_lang = detect_user_language(user_query)
    if user_lang != "English" and full:
        from src.iris_engine import translate_text
        yield {"type": "status", "content": f"Translating to {user_lang}..."}
        translated = translate_text(full, user_lang)
        if translated != full:
            full = translated
            yield {"type": "clear"}
            yield {"type": "token", "content": full}

    yield {"type": "raw_response", "content": full}


def run_stream(user_query: str, history: list, retriever: Any, settings: dict, is_complex: bool = False) -> Generator[Dict[str, str], None, None]:
    # 1. RAG
    context = ""
    if retriever is not None and len(user_query.split()) >= 3:
        is_contextual = False
        if history:
            pronouns = re.compile(r'\b(he|him|his|she|her|it|its|they|them|this|that)\b', re.IGNORECASE)
            if len(user_query.split()) < 6 or pronouns.search(user_query):
                is_contextual = True
        
        if not is_contextual:
            context = retriever.retrieve(user_query, top_k=3, category="coding")
            
    final_query = user_query
    if context:
        final_query = (
            f"<retrieved_context>\n{context}\n</retrieved_context>\n\n"
            f"You MUST use the reference architectures, layout patterns, and gorgeous single-file website templates provided in the retrieved context above to implement the gorgeous design, animations, typography, and styling for the website.\n\n"
            f"{final_query}"
        )
        
    from src.iris_engine import _language_directive
    final_query += _language_directive(user_query, role=ModelRole.CODE)
    
    # 2. History & Compaction
    optimized = [{"role": "user", "content": final_query}]
    if history:
        optimized = [{"role": m["role"], "content": m["content"]} for m in history] + optimized
        
    if is_complex:
        yield from _run_complex_coding(user_query, history, optimized, context, retriever, settings)
    else:
        yield from _run_simple_coding(user_query, history, optimized, settings)
