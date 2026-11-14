"""Ponto de implementação das regras declarativas do enunciado."""

import load_previous
from ast_nodes import (
    BinaryExpr,
    BinaryOperator,
    BoolLiteral,
    CallExpr,
    IdentifierExpr,
    TypeName,
    UnaryExpr,
    UnaryOperator,
)
from patterns import (
    Args,
    COND,
    EFFECT,
    IMM12,
    POW2,
    REG,
    Need,
    Pattern,
    Rule,
    imm12,
    neg_imm12,
    pow2,
    signed_literal,
)


def _has_type(expected):
    """Crie um predicado para o tipo já anotado pela análise semântica."""

    def predicate(node):
        return node.metadata.get("type") is expected

    return predicate


def catalogue():
    """Codifique o catálogo do enunciado com Rule e Pattern."""
    rules = [
        Rule(
            "int_literal",
            REG,
            Pattern(predicate=lambda node: signed_literal(node) is not None),
            1,
            "int_literal",
        ),
        Rule("bool_literal", REG, Pattern(BoolLiteral), 1, "bool_literal"),
        Rule("identifier", REG, Pattern(IdentifierExpr), 0, "identifier"),
        Rule("imm12", IMM12, Pattern(predicate=imm12), 0, "imm12"),
        Rule("pow2", POW2, Pattern(predicate=pow2), 0, "pow2"),
        Rule(
            "negate",
            REG,
            Pattern(UnaryExpr, UnaryOperator.NEGATE, (Need(REG),)),
            1,
            "negate",
        ),
    ]

    arithmetic = {
        BinaryOperator.ADD: "add",
        BinaryOperator.SUBTRACT: "subtract",
        BinaryOperator.MULTIPLY: "multiply",
        BinaryOperator.DIVIDE: "divide",
        BinaryOperator.REMAINDER: "remainder",
    }
    rules.extend(
        Rule(
            name,
            REG,
            Pattern(BinaryExpr, operator, (Need(REG), Need(REG))),
            1,
            name,
        )
        for operator, name in arithmetic.items()
    )
    rules.extend(
        [
            Rule(
                "add_immediate_right",
                REG,
                Pattern(
                    BinaryExpr,
                    BinaryOperator.ADD,
                    (Need(REG), Need(IMM12)),
                ),
                1,
                "add_immediate_right",
            ),
            Rule(
                "add_immediate_left",
                REG,
                Pattern(
                    BinaryExpr,
                    BinaryOperator.ADD,
                    (Need(IMM12), Need(REG)),
                ),
                1,
                "add_immediate_left",
            ),
            Rule(
                "subtract_immediate",
                REG,
                Pattern(
                    BinaryExpr,
                    BinaryOperator.SUBTRACT,
                    (Need(REG), Pattern(predicate=neg_imm12)),
                ),
                1,
                "subtract_immediate",
            ),
            Rule(
                "multiply_power_right",
                REG,
                Pattern(
                    BinaryExpr,
                    BinaryOperator.MULTIPLY,
                    (Need(REG), Need(POW2)),
                ),
                1,
                "multiply_power_right",
            ),
            Rule(
                "multiply_power_left",
                REG,
                Pattern(
                    BinaryExpr,
                    BinaryOperator.MULTIPLY,
                    (Need(POW2), Need(REG)),
                ),
                1,
                "multiply_power_left",
            ),
        ]
    )

    value_comparisons = {
        BinaryOperator.LESS: (1, "less"),
        BinaryOperator.GREATER: (1, "greater"),
        BinaryOperator.LESS_EQUAL: (2, "less_equal"),
        BinaryOperator.GREATER_EQUAL: (2, "greater_equal"),
        BinaryOperator.EQUAL: (2, "equal"),
        BinaryOperator.NOT_EQUAL: (2, "not_equal"),
    }
    for operator, (cost, name) in value_comparisons.items():
        pattern = Pattern(BinaryExpr, operator, (Need(REG), Need(REG)))
        rules.append(Rule(name, REG, pattern, cost, name))
        rules.append(
            Rule(name + "_condition", COND, pattern, 2, name + "_condition")
        )

    rules.extend(
        [
            Rule(
                "logical_not_value",
                REG,
                Pattern(UnaryExpr, UnaryOperator.NOT, (Need(REG),)),
                1,
                "logical_not_value",
            ),
            Rule(
                "logical_not_condition",
                COND,
                Pattern(UnaryExpr, UnaryOperator.NOT, (Need(COND),)),
                0,
                "logical_not_condition",
            ),
        ]
    )
    for operator, name in (
        (BinaryOperator.LOGICAL_AND, "logical_and"),
        (BinaryOperator.LOGICAL_OR, "logical_or"),
    ):
        pattern = Pattern(BinaryExpr, operator, (Need(COND), Need(COND)))
        rules.append(Rule(name + "_condition", COND, pattern, 0, name + "_condition"))
        rules.append(Rule(name + "_value", REG, pattern, 3, name + "_value"))

    rules.extend(
        [
            Rule(
                "bool_literal_condition",
                COND,
                Pattern(BoolLiteral),
                1,
                "bool_literal_condition",
            ),
            Rule(
                "bool_identifier_condition",
                COND,
                Pattern(IdentifierExpr, predicate=_has_type(TypeName.BOOL)),
                2,
                "bool_identifier_condition",
            ),
            Rule(
                "call_value",
                REG,
                Pattern(
                    CallExpr,
                    children=(Args(REG),),
                    predicate=lambda node: node.metadata.get("type")
                    in (TypeName.INT, TypeName.BOOL),
                ),
                1,
                "call_value",
            ),
            Rule(
                "call_effect",
                EFFECT,
                Pattern(CallExpr, children=(Args(REG),)),
                1,
                "call_effect",
            ),
            Rule(
                "bool_call_condition",
                COND,
                Pattern(
                    CallExpr,
                    children=(Args(REG),),
                    predicate=_has_type(TypeName.BOOL),
                ),
                3,
                "bool_call_condition",
            ),
        ]
    )
    return tuple(rules)
