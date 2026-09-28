"""Small deterministic regression rules, not a complete course correctness oracle."""

import re

from agents.schemas.resources import ExerciseResource, ResourceDraft


def brackets_match(sequence: str) -> bool:
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for char in sequence:
        if char in "([{":
            stack.append(char)
        elif char in pairs and (not stack or stack.pop() != pairs[char]):
            return False
    return not stack


def check_data_structure(resource: ResourceDraft) -> tuple[str, ...]:
    issues = []
    for text in all_text(resource.model_dump()):
        if re.search(
            r"二分查找(?:适用于|可以用于|支持)(?:任意)?无序(?:数组|序列)", text
        ) and not any(
            marker in text for marker in ("错误", "不正确", "不成立", "不能", "并非", "误区")
        ):
            issues.append("二分查找的有序前提错误")
    if isinstance(resource, ExerciseResource):
        for question in resource.questions:
            if "括号" not in question.prompt or "匹配" not in question.prompt:
                continue
            sequence = "".join(c for c in question.prompt if c in "()[]{}")
            if not sequence:
                continue
            answer = question.answer
            if question.question_type == "single_choice":
                answer = next(o.content for o in question.options if o.label == question.answer)
            if "不匹配" in answer:
                claimed = False
            elif "匹配" in answer:
                claimed = True
            else:
                continue
            if claimed != brackets_match(sequence):
                issues.append(f"题目{question.question_id}的括号匹配答案错误")
    return tuple(issues)


def all_text(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from all_text(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_text(item)
