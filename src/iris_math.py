import re
from typing import Optional

def get_math_prompt(identity: str) -> str:
    return (
        f"{identity}\n"
        "You are the Iris AI Math Core. Solve mathematical/algorithmic problems step-by-step. "
        "Use precise notation. Please reason step by step, and put your final answer within \\boxed{}. "
        "ANTI-POLLUTION RULE: If your solution requires writing code (like Python or C++), "
        "DO NOT use LaTeX or MathJax formatting (like $...$ or _{...}) inside the code block. "
        "Variable names and function names inside code must be plain ASCII identifiers only. "
        "LaTeX notation (\\boxed{}, $...$) is ONLY for the mathematical explanation text outside code blocks. "
        "IMPORTANT: For display math blocks, you MUST use $$ ... $$ and NEVER use \\[ ... \\]."
    )

def solve_math(user_text: str) -> Optional[str]:
    try:
        from sympy import symbols, solve, Eq, sympify, simplify
        from sympy.parsing.sympy_parser import (
            parse_expr, standard_transformations,
            implicit_multiplication_application, convert_xor
        )
    except ImportError:
        return None

    text = user_text.strip().rstrip('?').strip()
    has_math_prefix = bool(re.search(r'^(solve|calculate|what is|compute|evaluate)\s+', text, flags=re.IGNORECASE))
    text = re.sub(r'^(solve|calculate|what is|compute|evaluate)\s+', '', text, flags=re.IGNORECASE).strip()
    
    # Fast-path interceptor should ONLY handle pure math.
    # Dynamically check if English words are valid SymPy objects or explicit function calls.
    words = re.findall(r'[a-zA-Z]{2,}', text)
    if words:
        import sympy
        for w in words:
            if not (hasattr(sympy, w) or hasattr(sympy, w.capitalize()) or hasattr(sympy, w.lower())):
                # Allow it if it looks like an explicit function call, e.g., generic f(x) or arccos(x)
                if not re.search(rf'\b{re.escape(w)}\s*\(', text):
                    return None

    def normalise(expr: str) -> str:
        # Normalize Unicode math symbols BEFORE anything else
        expr = expr.replace('×', '*').replace('✕', '*').replace('✖', '*')
        expr = expr.replace('÷', '/').replace('⁄', '/')
        expr = expr.replace('−', '-').replace('–', '-').replace('—', '-')
        expr = expr.replace('²', '**2').replace('³', '**3')
        expr = expr.replace('π', 'pi')
        # Handle 'x' used as multiplication between numbers (e.g. 5x5 or 5 x 5)
        expr = re.sub(r'(?<=\d)\s*[xX]\s*(?=\d)', '*', expr)
        # Implicit multiplication: 2x → 2*x
        expr = re.sub(r'([0-9])([a-zA-Z])', r'\1*\2', expr)
        expr = re.sub(r'\^', '**', expr)
        return expr

    transformations = standard_transformations + (implicit_multiplication_application, convert_xor)

    if '=' in text:
        parts = text.split('=', 1)
        lhs_raw, rhs_raw = normalise(parts[0].strip()), normalise(parts[1].strip())
        var_names = sorted(set(re.findall(r'\b([a-zA-Z])\b', lhs_raw + ' ' + rhs_raw)))
        if not var_names:
            return None
        try:
            var_syms = {v: symbols(v) for v in var_names}
            lhs = parse_expr(lhs_raw, local_dict=var_syms, transformations=transformations)
            rhs = parse_expr(rhs_raw, local_dict=var_syms, transformations=transformations)
            eq = Eq(lhs, rhs)
            solutions = solve(eq, list(var_syms.values()))
        except Exception:
            return None
        if not solutions:
            return "This equation has no solution."
        if isinstance(solutions, list):
            if len(solutions) == 1:
                return f"{var_names[0]} = {solutions[0]}"
            return "Solutions: " + ", ".join(f"{var_names[0]} = {s}" for s in solutions)
        if isinstance(solutions, dict):
            return ", ".join([f"{k} = {v}" for k, v in solutions.items()])
        return str(solutions)
    else:
        if not re.search(r'\d', text):
            return None
        normalized = normalise(text)
        # If after normalization it's purely arithmetic (no variables), evaluate directly
        has_variables = bool(re.findall(r'\b([a-zA-Z])\b', normalized.replace('pi', '')))
        try:
            expr = parse_expr(normalized, transformations=transformations)
            if has_variables:
                # Require explicit math symbols or a math command if variables are present
                has_operators = bool(re.search(r'[\+\-\*\/\^\(\)\=\²\³\×\✕\✖\÷\⁄\−\–\—]', user_text))
                if not (has_math_prefix or has_operators):
                    return None
                simplified = simplify(expr)
                # If simplify doesn't actually change anything meaningful, maybe we shouldn't just echo it
                return str(simplified)
            result = expr.evalf()
            if result.is_integer:
                return str(int(result))
            elif result.is_Float:
                rounded = round(float(result), 6)
                if rounded == int(rounded):
                    return str(int(rounded))
                return str(rounded)
            else:
                return str(result)
        except Exception:
            return None

    arith_text = re.sub(
        r'^(?:what\s+is|solve|find|calculate|compute|simplify|evaluate)\s+',
        '', text, flags=re.IGNORECASE
    ).strip()
    if re.findall(r'\b([a-zA-Z])\b', arith_text):
        return None
    arith = normalise(arith_text)
    if not re.fullmatch(r'[\d\s\+\-\*\/\(\)\.]+', arith):
        return None
    try:
        res = simplify(sympify(arith))
        return str(int(res)) if res == int(res) else str(res)
    except Exception:
        return None





from typing import Generator, Dict, Any
from src.iris_engine import ModelRole, load_model, unload_model, _keep_loaded, _stream_tokens, load_generation_config
from src.context_compactor import auto_compact_for_role
from src.iris_engine import detect_user_language, _language_directive

def run_stream(user_query: str, history: list, retriever: Any, settings: dict) -> Generator[Dict[str, str], None, None]:
    yield {"type": "status", "content": "Solving..."}
    
    # 1. RAG
    context = ""
    if retriever is not None and len(user_query.split()) >= 12:
        is_contextual = False
        if history:
            pronouns = re.compile(r'\b(he|him|his|she|her|it|its|they|them|this|that)\b', re.IGNORECASE)
            if len(user_query.split()) < 6 or pronouns.search(user_query):
                is_contextual = True
        
        if not is_contextual:
            context = retriever.retrieve(user_query, top_k=3, category="math")
            
    final_query = user_query
    if context:
        final_query = (
            f"<retrieved_context>\n{context}\n</retrieved_context>\n\n"
            f"If the retrieved context is relevant, use it. Otherwise, ignore it.\n\n"
            f"{final_query}"
        )
        
    final_query += _language_directive(user_query)
    
    # 2. History & Compaction
    optimized = [{"role": "user", "content": final_query}]
    if history:
        cfg = load_generation_config()
        profile = str(cfg.get("compacting_profile", "medium")).lower()
        num_history = 2 if profile == "aggressive" else (10 if profile == "low" else 5)
        recent = history[-num_history:]
        optimized = [{"role": m["role"], "content": m["content"]} for m in recent] + optimized

    optimized, _ = auto_compact_for_role(optimized, role=ModelRole.MATH, max_output_tokens=4096)
    
    # 3. Generation
    full = ""
    for ev in _stream_tokens(ModelRole.MATH, optimized, max_tokens=4096, temperature=0.2, think_mode="show"):
        yield ev
        if ev["type"] == "token":
            full += ev["content"]
            
    if not _keep_loaded:
        unload_model()
        
    yield {"type": "raw_response", "content": full}
