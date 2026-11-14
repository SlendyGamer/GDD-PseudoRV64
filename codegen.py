"""Pontos de implementação da geração de comandos e expressões."""

import load_previous
import ir as I
from ast_nodes import (
    Assignment,
    Block,
    CallStmt,
    Expr,
    IfStmt,
    PrintStmt,
    ReturnStmt,
    StringLiteral,
    TypeName,
    VarDecl,
    WhileStmt,
)
from catalogue import catalogue
from patterns import COND, EFFECT, IMM12, POW2, REG, signed_literal
from selector import Selector


class CodeGenerator:
    """Coordene comandos ad hoc e seleção de expressões com DP."""

    BINARY_INSTRUCTIONS = {
        "add": I.Add,
        "subtract": I.Sub,
        "multiply": I.Mul,
        "divide": I.Div,
        "remainder": I.Rem,
    }

    def __init__(self):
        self.selector = Selector(catalogue())
        self.program = None
        self.context = None

    def generate(self, program):
        """Traduza funções e comandos. Selecione expressões com DP."""
        result = I.ProgramIR()
        functions = []

        # Registra todas as funções antes de emitir chamadas entre elas
        for declaration in program.functions:
            function = I.FunctionIR(declaration.metadata["symbol"])
            result.functions.append(function)
            functions.append((declaration, function))

        self.program = result
        for declaration, function in functions:
            self.context = I.Context(function, result)
            for index, parameter in enumerate(declaration.parameters):
                destination = self.context.variable(parameter.metadata["symbol"])
                self.context.emit(I.Param(destination, index, origin=parameter.span))

            self.statement(declaration.body)
            if (
                declaration.return_type is TypeName.VOID
                and (
                    not function.instructions
                    or not isinstance(function.instructions[-1], I.Return)
                )
            ):
                self.context.emit(I.Return(None, origin=declaration.body.span))

        return result

    def expression(self, node, result_class, true_label=None, false_label=None):
        """Selecione e reconstrua uma expressão, preservando curto-circuito."""
        table = self.selector.analyze(node)
        return self._reconstruct(
            node,
            result_class,
            table,
            true_label=true_label,
            false_label=false_label,
        )

    def statement(self, node):
        """Traduza um comando ad hoc."""
        if isinstance(node, Block):
            for child in node.statements:
                self.statement(child)
            return

        if isinstance(node, VarDecl):
            if node.initializer is not None:
                value = self.expression(node.initializer, REG)
                destination = self.context.variable(node.metadata["symbol"])
                self.context.emit(I.Move(destination, value, origin=node.span))
            return

        if isinstance(node, Assignment):
            value = self.expression(node.value, REG)
            destination = self.context.variable(node.target.metadata["symbol"])
            self.context.emit(I.Move(destination, value, origin=node.span))
            return

        if isinstance(node, CallStmt):
            self.expression(node.call, EFFECT)
            return

        if isinstance(node, IfStmt):
            self._if_statement(node)
            return

        if isinstance(node, WhileStmt):
            self._while_statement(node)
            return

        if isinstance(node, ReturnStmt):
            value = None if node.value is None else self.expression(node.value, REG)
            self.context.emit(I.Return(value, origin=node.span))
            return

        if isinstance(node, PrintStmt):
            self._print_statement(node)
            return

        raise TypeError(f"comando desconhecido: {type(node).__name__}")

    def _if_statement(self, node):
        true_label = self.context.label()
        false_label = self.context.label()
        end_label = false_label if node.else_block is None else self.context.label()

        self.expression(node.condition, COND, true_label, false_label)
        self._label(true_label)
        self.statement(node.then_block)
        self.context.emit(I.Jump(end_label, origin=node.span))

        if node.else_block is not None:
            self._label(false_label)
            self.statement(node.else_block)
            self.context.emit(I.Jump(end_label, origin=node.span))
        self._label(end_label)

    def _while_statement(self, node):
        condition_label = self.context.label()
        body_label = self.context.label()
        end_label = self.context.label()

        self.context.emit(I.Jump(condition_label, origin=node.span))
        self._label(condition_label)
        self.expression(node.condition, COND, body_label, end_label)
        self._label(body_label)
        self.statement(node.body)
        self.context.emit(I.Jump(condition_label, origin=node.span))
        self._label(end_label)

    def _print_statement(self, node):
        for item in node.items:
            if isinstance(item, StringLiteral):
                reference = self.context.string(item.value)
                self.context.emit(I.PrintString(reference, origin=item.span))
                continue

            if not isinstance(item, Expr):
                name = type(item).__name__
                raise TypeError(f"item de impressão desconhecido: {name}")
            value = self.expression(item, REG)
            instruction = (
                I.PrintBool
                if item.metadata.get("type") is TypeName.BOOL
                else I.PrintInt
            )
            self.context.emit(instruction(value, origin=item.span))

        newline = self.context.string("\n")
        self.context.emit(I.PrintString(newline, origin=node.span))

    def _reconstruct(
        self,
        node,
        result_class,
        table,
        true_label=None,
        false_label=None,
    ):
        choice = table.lookup(node, result_class)
        if choice is None:
            span = node.span
            raise ValueError(
                f"expressão sem cobertura {result_class.value} "
                f"em {span.start_line}:{span.start_column}"
            )
        if result_class is COND and (true_label is None or false_label is None):
            raise ValueError("destinos ausentes para expressão condicional")

        action = getattr(self, "_emit_" + choice.rule.action, None)
        if action is None:
            raise ValueError(f"ação desconhecida: {choice.rule.action}")
        return action(node, choice, table, true_label, false_label)

    def _subproblem(
        self,
        choice,
        table,
        index,
        true_label=None,
        false_label=None,
    ):
        node, result_class = choice.subproblems[index]
        return self._reconstruct(
            node,
            result_class,
            table,
            true_label=true_label,
            false_label=false_label,
        )

    def _label(self, label):
        self.context.emit(I.LabelInstr(label))

    def _emit_int_literal(self, node, choice, table, true_label, false_label):
        destination = self.context.temp()
        self.context.emit(I.Li(destination, signed_literal(node), origin=node.span))
        return destination

    def _emit_bool_literal(self, node, choice, table, true_label, false_label):
        destination = self.context.temp()
        self.context.emit(I.Li(destination, int(node.value), origin=node.span))
        return destination

    def _emit_identifier(self, node, choice, table, true_label, false_label):
        return self.context.variable(node.metadata["symbol"])

    def _emit_imm12(self, node, choice, table, true_label, false_label):
        return signed_literal(node)

    def _emit_pow2(self, node, choice, table, true_label, false_label):
        return signed_literal(node).bit_length() - 1

    def _emit_negate(self, node, choice, table, true_label, false_label):
        source = self._subproblem(choice, table, 0)
        destination = self.context.temp()
        self.context.emit(I.Neg(destination, source, origin=node.span))
        return destination

    def _emit_binary(self, node, choice, table, true_label, false_label):
        left = self._subproblem(choice, table, 0)
        right = self._subproblem(choice, table, 1)
        destination = self.context.temp()
        instruction = self.BINARY_INSTRUCTIONS[choice.rule.action]
        self.context.emit(instruction(destination, left, right, origin=node.span))
        return destination

    _emit_add = _emit_binary
    _emit_subtract = _emit_binary
    _emit_multiply = _emit_binary
    _emit_divide = _emit_binary
    _emit_remainder = _emit_binary

    def _emit_add_immediate(self, node, choice, table, true_label, false_label):
        first = self._subproblem(choice, table, 0)
        second = self._subproblem(choice, table, 1)
        if choice.rule.action == "add_immediate_right":
            source, immediate = first, second
        else:
            immediate, source = first, second
        destination = self.context.temp()
        self.context.emit(I.Addi(destination, source, immediate, origin=node.span))
        return destination

    _emit_add_immediate_right = _emit_add_immediate
    _emit_add_immediate_left = _emit_add_immediate

    def _emit_subtract_immediate(
        self, node, choice, table, true_label, false_label
    ):
        source = self._subproblem(choice, table, 0)
        immediate = -signed_literal(node.right)
        destination = self.context.temp()
        self.context.emit(I.Addi(destination, source, immediate, origin=node.span))
        return destination

    def _emit_multiply_power(self, node, choice, table, true_label, false_label):
        first = self._subproblem(choice, table, 0)
        second = self._subproblem(choice, table, 1)
        if choice.rule.action == "multiply_power_right":
            source, shift = first, second
        else:
            shift, source = first, second
        destination = self.context.temp()
        self.context.emit(I.Slli(destination, source, shift, origin=node.span))
        return destination

    _emit_multiply_power_right = _emit_multiply_power
    _emit_multiply_power_left = _emit_multiply_power

    def _emit_comparison_value(
        self, node, choice, table, true_label, false_label
    ):
        left = self._subproblem(choice, table, 0)
        right = self._subproblem(choice, table, 1)
        action = choice.rule.action
        destination = self.context.temp()

        if action == "less":
            self.context.emit(I.Slt(destination, left, right, origin=node.span))
        elif action == "greater":
            self.context.emit(I.Slt(destination, right, left, origin=node.span))
        elif action in ("less_equal", "greater_equal"):
            temporary = self.context.temp()
            lhs, rhs = (
                (right, left) if action == "less_equal" else (left, right)
            )
            self.context.emit(I.Slt(temporary, lhs, rhs, origin=node.span))
            self.context.emit(I.Seqz(destination, temporary, origin=node.span))
        else:
            temporary = self.context.temp()
            self.context.emit(I.Xor(temporary, left, right, origin=node.span))
            instruction = I.Seqz if action == "equal" else I.Snez
            self.context.emit(instruction(destination, temporary, origin=node.span))
        return destination

    _emit_less = _emit_comparison_value
    _emit_greater = _emit_comparison_value
    _emit_less_equal = _emit_comparison_value
    _emit_greater_equal = _emit_comparison_value
    _emit_equal = _emit_comparison_value
    _emit_not_equal = _emit_comparison_value

    def _emit_comparison_condition(
        self, node, choice, table, true_label, false_label
    ):
        left = self._subproblem(choice, table, 0)
        right = self._subproblem(choice, table, 1)
        action = choice.rule.action
        branches = {
            "less_condition": (I.Blt, left, right),
            "greater_condition": (I.Blt, right, left),
            "less_equal_condition": (I.Bge, right, left),
            "greater_equal_condition": (I.Bge, left, right),
            "equal_condition": (I.Beq, left, right),
            "not_equal_condition": (I.Bne, left, right),
        }
        instruction, lhs, rhs = branches[action]
        self.context.emit(instruction(lhs, rhs, true_label, origin=node.span))
        self.context.emit(I.Jump(false_label, origin=node.span))

    _emit_less_condition = _emit_comparison_condition
    _emit_greater_condition = _emit_comparison_condition
    _emit_less_equal_condition = _emit_comparison_condition
    _emit_greater_equal_condition = _emit_comparison_condition
    _emit_equal_condition = _emit_comparison_condition
    _emit_not_equal_condition = _emit_comparison_condition

    def _emit_logical_not_value(
        self, node, choice, table, true_label, false_label
    ):
        source = self._subproblem(choice, table, 0)
        destination = self.context.temp()
        self.context.emit(I.Seqz(destination, source, origin=node.span))
        return destination

    def _emit_logical_not_condition(
        self, node, choice, table, true_label, false_label
    ):
        self._subproblem(choice, table, 0, false_label, true_label)

    def _emit_logical_condition(
        self, node, choice, table, true_label, false_label
    ):
        middle = self.context.label()
        if choice.rule.action.startswith("logical_and"):
            self._subproblem(choice, table, 0, middle, false_label)
        else:
            self._subproblem(choice, table, 0, true_label, middle)
        self._label(middle)
        self._subproblem(choice, table, 1, true_label, false_label)

    _emit_logical_and_condition = _emit_logical_condition
    _emit_logical_or_condition = _emit_logical_condition

    def _emit_logical_value(self, node, choice, table, true_label, false_label):
        destination = self.context.temp()
        true_path = self.context.label()
        false_path = self.context.label()
        end = self.context.label()

        self._emit_logical_condition(
            node,
            choice,
            table,
            true_path,
            false_path,
        )
        self._label(true_path)
        self.context.emit(I.Li(destination, 1, origin=node.span))
        self.context.emit(I.Jump(end, origin=node.span))
        self._label(false_path)
        self.context.emit(I.Li(destination, 0, origin=node.span))
        self._label(end)
        return destination

    _emit_logical_and_value = _emit_logical_value
    _emit_logical_or_value = _emit_logical_value

    def _emit_bool_literal_condition(
        self, node, choice, table, true_label, false_label
    ):
        target = true_label if node.value else false_label
        self.context.emit(I.Jump(target, origin=node.span))

    def _emit_bool_identifier_condition(
        self, node, choice, table, true_label, false_label
    ):
        source = self.context.variable(node.metadata["symbol"])
        self.context.emit(I.Bnez(source, true_label, origin=node.span))
        self.context.emit(I.Jump(false_label, origin=node.span))

    def _call_arguments(self, choice, table):
        return [
            self._reconstruct(node, result_class, table)
            for node, result_class in choice.subproblems
        ]

    def _emit_call_value(self, node, choice, table, true_label, false_label):
        arguments = self._call_arguments(choice, table)
        destination = self.context.temp()
        self.context.emit(
            I.Call(
                destination,
                node.metadata["symbol"],
                arguments,
                origin=node.span,
            )
        )
        return destination

    def _emit_call_effect(self, node, choice, table, true_label, false_label):
        arguments = self._call_arguments(choice, table)
        self.context.emit(
            I.Call(None, node.metadata["symbol"], arguments, origin=node.span)
        )

    def _emit_bool_call_condition(
        self, node, choice, table, true_label, false_label
    ):
        arguments = self._call_arguments(choice, table)
        destination = self.context.temp()
        self.context.emit(
            I.Call(
                destination,
                node.metadata["symbol"],
                arguments,
                origin=node.span,
            )
        )
        self.context.emit(I.Bnez(destination, true_label, origin=node.span))
        self.context.emit(I.Jump(false_label, origin=node.span))
