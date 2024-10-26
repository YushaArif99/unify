import inspect
import json
import traceback
import importlib
import os.path
from typing import Optional

import unify
from .system_messages import (
    CODING_SYS_MESSAGE_BASE,
    INIT_CODING_SYS_MESSAGE,
    UPDATING_CODING_SYS_MESSAGE,
    DOCSTRING_SYS_MESSAGE_HEAD,
    DOCSTRING_SYS_MESSAGE_FIRST_CONTEXT,
    DOCSTRING_SYS_MESSAGE_EXTRA_CONTEXT,
    DOCSTRING_SYS_MESSAGE_TAIL,
)

MODEL = "gpt-4o@openai"


IMPLEMENTATIONS = dict()
MODULE_PATH = "implementations.py"

INTERACTIVE = True

FN_TREE = dict()


def set_interactive():
    global INTERACTIVE
    INTERACTIVE = True


def set_non_interactive():
    global INTERACTIVE
    INTERACTIVE = False


def interactive_mode():
    global INTERACTIVE
    return INTERACTIVE


class Interactive:

    def __enter__(self):
        set_interactive()

    def __exit__(self, exc_type, exc_val, exc_tb):
        set_non_interactive()


def _formatted(inp: str) -> str:
    return inp if inp[-1] == "\n" else inp + "\n"


def implement(fn: callable, module_path: Optional[str] = None):

    global MODULE_PATH
    if module_path is None:
        module_path = MODULE_PATH
        full_module_path = os.path.join(os.getcwd(), MODULE_PATH)

    def _load_module(module_name: str):
        if not os.path.exists(full_module_path):
            with open(full_module_path, "w+") as file:
                file.write("import unify\n\n\n")
            return
        while True:
            try:
                return importlib.reload(
                    importlib.import_module(module_name),
                )
            except Exception as e:
                print(
                    "\nOops, seems like there was an error loading " "our new module.",
                    e,
                )
                input(
                    "Don't worry about any undefined imaginary functions which may "
                    "have red underlines shown in your IDE etc., we just need to fix "
                    "the specific issue mentioned above and then "
                    "move to the next step.\n"
                    f"Open the file `{full_module_path}` and fix the issue "
                    "mentioned above, "
                    "(don't forget to ctrl-S to save in your IDE/editor!), "
                    "then press enter once you're happy 👌\n",
                )

    global IMPLEMENTATIONS
    module = _load_module(module_path.rstrip(".py"))
    for name, obj in inspect.getmembers(module):
        if callable(obj):
            IMPLEMENTATIONS[obj.__name__] = obj

    def _populate_dev_system_message(template: str) -> str:
        return (
            template.replace(
                "{name}",
                name,
            )
            .replace(
                "{docstring}",
                docstring.lstrip("\n").rstrip(" ").rstrip("\n"),
            )
            .replace(
                "{signature}",
                signature,
            )
        )

    def _populate_docstring_context_system_message(
        template: str,
        child_name: str,
        parent_name: str,
        parent_implementation: str,
        calling_line: str,
    ) -> str:
        return (
            template.replace(
                "{child_name}",
                child_name,
            )
            .replace(
                "{parent_name}",
                parent_name,
            )
            .replace(
                "{parent_implementation}",
                parent_implementation,
            )
            .replace(
                "{calling_line}",
                calling_line,
            )
        )

    name = fn.__name__ if fn.__name__ is not None else ""
    docstring = fn.__doc__ if fn.__doc__ is not None else ""
    signature = str(inspect.signature(fn))
    client = unify.Unify(MODEL, cache=True)
    docstring_client = unify.Unify(MODEL, cache=True)
    first_line = f"def {name}{signature}:"
    init_system_message = _populate_dev_system_message(INIT_CODING_SYS_MESSAGE)
    update_system_message = _populate_dev_system_message(UPDATING_CODING_SYS_MESSAGE)
    system_message_base = _populate_dev_system_message(CODING_SYS_MESSAGE_BASE)
    init_system_message += system_message_base
    update_system_message += system_message_base
    client.set_system_message(init_system_message)
    client.set_stateful(True)

    def _get_imports(response):
        top_half = response.split(first_line)[0].rstrip("\n")
        lines = top_half.split("\n")
        imports = list()

        for line in reversed(lines):
            if not line.startswith("import ") and not line.startswith("from "):
                break
            imports.append(line)
        return "\n".join(reversed(imports))

    def _parse_src_code(fn_name, context=None):
        if context is None:
            with open(full_module_path, "r") as file:
                context = file.read()
        lines = context.split("\n")
        starting_line = [f"def {fn_name}(" in ln for ln in lines].index(True)
        valid_lines = lines[starting_line : starting_line + 1]
        for line in lines[starting_line + 1 :]:
            line_len = len(line)
            if (line_len > 4 and line[0:4] != "    ") or (
                line_len <= 4 and line.strip(" ").strip("\n") != ""
            ):
                break
            valid_lines.append(line)
        return "\n".join(valid_lines)

    def _remove_docstring(src_code: str) -> str:
        lines = src_code.splitlines()
        removing = False
        new_lines = list()
        for ln in lines:
            if ln == '    """':
                removing = not removing
                continue
            if removing:
                continue
            new_lines.append(ln)
        return "\n".join(new_lines)

    def _inject_docstring(src_code: str, dcstr: str) -> str:
        src_code = _remove_docstring(src_code)
        lines = src_code.splitlines()
        def_idx = ["def " in ln for ln in lines].index(True)
        return "\n".join(
            lines[0 : def_idx + 1] + [f'    """{dcstr}"""'] + lines[def_idx + 1 :],
        )

    def _generate_code():
        response = client.generate(
            f"please implement the function `{name}` by strictly following the "
            "instructions in the original system message, and also carefully following "
            "any instructions in the full chat history, if any is present:",
        )
        assert (
            first_line in response,
            "Model failed to follow the formatting instructions.",
        )
        return (
            _get_imports(response),
            _inject_docstring(_parse_src_code(name, response), docstring),
            response,
        )

    def _generate_function_spec(fn_name):
        response = docstring_client.generate(
            f"please implement the function definition for `{fn_name}` as described in "
            "the format described in the system message.",
        )
        return _parse_src_code(fn_name, response), response

    def _load_function(fn_name: str):
        while True:
            try:
                return getattr(
                    _load_module(module_path.rstrip(".py")),
                    fn_name,
                )
            except Exception as e:
                print(
                    "Hmmm, we loaded module without any errors, "
                    "but there was an error trying to load the function",
                    e,
                )
                input(
                    f"Open file `{full_module_path}` and fix the issue mentioned "
                    "above, then press enter once you're done 👌\n",
                )

    def _write_to_file(*, fn_name, imports="", implementation=""):
        with open(full_module_path, "r") as file:
            content = file.read()
        if f"def {fn_name}" not in content:
            new_content = imports + content + implementation
            with open(full_module_path, "w") as file:
                file.write(_formatted(new_content))
            return
        src_code = _parse_src_code(fn_name)
        new_content = imports + content.replace(src_code, implementation)
        with open(full_module_path, "w") as file:
            file.write(_formatted(new_content))

    def _remove_unify_decorator_if_present(fn_name: str):
        with open(full_module_path, "r") as file:
            content = file.read()
        lines = content.splitlines()
        fn_line_no = [f"def {fn_name}" in ln for ln in lines].index(True)
        has_decorator = lines[fn_line_no - 1] == "@unify.implement"
        if not has_decorator:
            return
        with open(full_module_path, "w") as file:
            file.write(
                _formatted("\n".join(lines[0 : fn_line_no - 1] + lines[fn_line_no:])),
            )

    def _step_loop(this_client, assistant_msg="") -> str:
        if assistant_msg:
            print(assistant_msg)
        assistant_questions = (
            "\nIs there anything you would like me to change? "
            "If so, then please respond in the following format:\n"
            '"Yes: {your explanation}"\n\n'
            "If you would like to make updates yourself, then you can directly "
            f"modify the source code in `{full_module_path}`.\n"
            "Simply respond in the following format once "
            "you've made the changes, and then I can take another look:\n"
            '"Reload: {your explanation}"\n\n'
            "Finally, if you're happy with these edits "
            "and would like to move onto the next function, "
            "then please respond in the following format:\n"
            '"Next: {your explanation}"\n\n'
        )
        response = input(assistant_questions).strip("'").strip('"')
        if response[0:4].lower() == "next":
            return "next"
        elif response[0:6].lower() == "reload":
            loaded_implementation = _parse_src_code(name)
            this_client.append_messages(
                [
                    {
                        "role": "user",
                        "content": response + ". Hers is the new implementation:"
                        f"\n{loaded_implementation}",
                    },
                ],
            )
            return "reload"
        elif response[0:3].lower() != "yes":
            print(
                "Please respond in one of the following formats:\n"
                "Yes: {your explanation}\n"
                "No: {your explanation}",
            )
            return "invalid"
        this_client.append_messages(
            [
                {"role": "assistant", "content": assistant_questions},
                {"role": "user", "content": response},
            ],
        )
        return "yes"

    def _add_child_functions_to_state(implementation: str):
        segments = [s.split("(")[0] for s in implementation.split(" ") if "(" in s]
        segments = [
            s
            for s in segments
            if s.replace("_", "").isalnum() and s == s.lower() and s != name
        ]
        if name not in FN_TREE:
            FN_TREE[name] = dict()
        for s in segments:
            FN_TREE[name][s] = dict()
        if segments:
            return segments[0]

    def _add_args_to_system_msg(*args, **kwargs):
        client.set_system_message(
            client.system_message.replace(
                "{args}",
                str(args)[1:-1],
            ).replace(
                "{kwargs}",
                str(kwargs)[1:-1].replace("'", "").replace(": ", "="),
            ),
        )

    def _get_fn(*args, **kwargs):
        global IMPLEMENTATIONS
        if name in IMPLEMENTATIONS:
            _remove_unify_decorator_if_present(name)
            print(f"\n`{name}` is already implemented, stepping inside.\n")
            return IMPLEMENTATIONS[name]
        print(f"We'll now work together to implement the function `{name}`.\n")
        _add_args_to_system_msg(*args, **kwargs)
        imports, implementation, llm_response = _generate_code()
        client.set_system_message(update_system_message)
        _add_args_to_system_msg(*args, **kwargs)
        _write_to_file(fn_name=name, imports=imports, implementation=implementation)
        if interactive_mode():
            should_continue = True
            assistant_msg = llm_response
            while should_continue:
                mode = _step_loop(client, assistant_msg)
                if mode == "reload":
                    assistant_msg = (
                        "Here is the latest implementation (following any changes "
                        "you may have made):"
                        f"\n\n{_parse_src_code(name)}"
                    )
                should_continue, should_update = {
                    "yes": (True, True),
                    "next": (False, False),
                    "reload": (True, False),
                    "invalid": (True, False),
                }[mode]
                if not should_update:
                    continue
                imports, implementation, llm_response = _generate_code()
                assistant_msg = llm_response
                _write_to_file(
                    fn_name=name,
                    imports=imports,
                    implementation=implementation,
                )
        _remove_unify_decorator_if_present(name)
        fn_implemented = _load_function(name)
        first_child = _add_child_functions_to_state(implementation)
        message = (
            "\nGreat! Now that we have an "
            f"implementation in place for `{name}`, "
            "let's decide what to work on next!\n"
            "The total set of functions being worked on within the uppermost "
            "`unify.implement` context are as follows:"
            "\n\n"
            f"{json.dumps(FN_TREE, indent=4)}"
            "\n\n"
            "Functions with empty dicts are not yet implemented, "
            "functions with `True` are implemented but don't have children, "
            "and functions with sub-dicts are implemented using those child functions. "
            "We'll continue to follow the ordering of the call stack.\n"
        )
        if first_child:
            message += (
                f"Therefore, we will work on implementing `{first_child}` next.\n"
                "A quick reminder that you can CTRL-C at any time, and we will simply "
                "pick up where we left off next time you run the `unify.implement` "
                "decorated function.\n"
                f"Otherwise, if you're happy for us to work on `{first_child}` "
                "then just press enter and we'll get started 👌\n"
            )
        input(message)
        IMPLEMENTATIONS[name] = fn_implemented
        _write_to_file(
            fn_name=name,
            imports=imports,
            implementation=implementation,
        )
        return fn_implemented

    def _add_new_function_spec_w_implement_decorator(name_error, tracebk):
        system_message = DOCSTRING_SYS_MESSAGE_HEAD.replace("{name}", name_error.name)
        context = list()
        first_context = True
        parent_name = None
        for line in reversed(tracebk.split("\n")):
            if not line or line[0] != " ":
                continue
            context.append(line)
            if line[0:8] == '  File "':
                if first_context:
                    parent_name = context[1].split(",")[-1].split(" ")[-1]
                    system_message += _populate_docstring_context_system_message(
                        DOCSTRING_SYS_MESSAGE_FIRST_CONTEXT,
                        child_name=name_error.name,
                        parent_name=parent_name,
                        parent_implementation=_parse_src_code(parent_name),
                        calling_line=context[0].lstrip(" "),
                    )
                    first_context = False
                else:
                    child_name = parent_name
                    parent_name = context[1].split(",")[-1].split(" ")[-1]
                    system_message += _populate_docstring_context_system_message(
                        DOCSTRING_SYS_MESSAGE_EXTRA_CONTEXT,
                        child_name=child_name,
                        parent_name=parent_name,
                        parent_implementation=_parse_src_code(parent_name),
                        calling_line=context[0].lstrip(" "),
                    )
                context.clear()
                if parent_name == name:
                    break

        system_message += DOCSTRING_SYS_MESSAGE_TAIL.replace("{name}", name_error.name)
        docstring_client.set_system_message(system_message)

    def _get_fn_spec(name_error, tracebk):
        _add_new_function_spec_w_implement_decorator(name_error, tracebk)
        function_spec, llm_response = _generate_function_spec(name_error.name)
        function_spec = "\n\n@unify.implement\n" + function_spec
        _write_to_file(fn_name=name_error.name, implementation=function_spec)
        if interactive_mode():
            should_continue = True
            assistant_msg = llm_response
            while should_continue:
                mode = _step_loop(docstring_client, assistant_msg)
                if mode == "reload":
                    assistant_msg = (
                        "Here is the latest implementation (following any changes "
                        "you may have made):"
                        f"\n\n{_parse_src_code(name)}"
                    )
                should_continue, should_update = {
                    "yes": (True, True),
                    "next": (False, False),
                    "reload": (True, False),
                    "invalid": (True, False),
                }[mode]
                if not should_update:
                    continue
                function_spec, llm_response = _generate_function_spec(
                    name_error.name,
                )
                assistant_msg = llm_response
                _write_to_file(
                    fn_name=name_error.name,
                    implementation=function_spec,
                )

        print(
            "\nGreat, I'm glad we're both happy with the specification for "
            f"`{name_error.name}`! Let's now make a start on the implementation, "
            f"and iterate on this together as before...",
        )

    def _execute_with_implement(func: callable, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except NameError as ne:
            print(
                f"\nOkay, so it seems like `{ne.name}` is not yet implemented, "
                "let's define the function specification together first, "
                "before moving onto the implementation in the next step.\n"
                "I'll make a first attempt based on the call stack, and then you "
                "can give me feedback and we can iterate together 🔁\n",
            )
            _get_fn_spec(ne, traceback.format_exc())
        return _load_function(func.__name__)(*args, **kwargs)

    def implemented(*args, **kwargs):
        return _execute_with_implement(_get_fn(*args, **kwargs), *args, **kwargs)

    return implemented
