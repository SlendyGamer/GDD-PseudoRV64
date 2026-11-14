"""Ponto de implementação do reconhecimento de padrões e custos mínimos."""

from patterns import *


class Selector:
    """Selecione coberturas sem executar expressões ou emitir instruções."""

    def __init__(self, rules):
        self.rules = tuple(rules)

    def analyze(self, expr):
        """Calcule mínimos por nó/classe sem emitir instruções."""
        table = SelectionTable()
        pending = [(expr, False)]
        analyzed = set()

        while pending:
            node, ready = pending.pop()
            node_id = id(node)
            if node_id in analyzed:
                continue
            if not ready:
                pending.append((node, True))
                pending.extend((child, False) for child in reversed(children(node)))
                continue

            self._analyze_node(node, table)
            analyzed.add(node_id)

        return table

    def _analyze_node(self, node, table):
        """Escolha a regra de menor custo para cada classe oferecida."""
        for rule in self.rules:
            subproblems = self._match(node, rule.pattern)
            if subproblems is None:
                continue

            choices = [table.lookup(child, result) for child, result in subproblems]
            if any(choice is None for choice in choices):
                continue

            cost = rule.cost + sum(choice.cost for choice in choices)
            current = table.lookup(node, rule.result)
            if current is None or cost < current.cost:
                table.put(
                    node,
                    rule.result,
                    Choice(cost, rule, subproblems),
                )

    def _match(self, node, pattern):
        """Reconheça um padrão e devolva os subproblemas na ordem da fonte."""
        if pattern.kind is not None and not isinstance(node, pattern.kind):
            return None
        if (
            pattern.operator is not None
            and getattr(node, "operator", None) != pattern.operator
        ):
            return None
        if pattern.predicate is not None and not pattern.predicate(node):
            return None

        node_children = children(node)
        pattern_children = pattern.children
        if len(pattern_children) == 1 and isinstance(pattern_children[0], Args):
            if not isinstance(node, CallExpr):
                return None
            result = pattern_children[0].result
            return tuple((child, result) for child in node_children)

        # Um predicado sem filhos reconhece a subárvore como uma unidade
        if pattern.predicate is not None and not pattern_children:
            return ()
        if len(node_children) != len(pattern_children):
            return None

        subproblems = []
        for child, child_pattern in zip(node_children, pattern_children):
            if isinstance(child_pattern, Need):
                subproblems.append((child, child_pattern.result))
                continue
            if not isinstance(child_pattern, Pattern):
                return None
            nested = self._match(child, child_pattern)
            if nested is None:
                return None
            subproblems.extend(nested)
        return tuple(subproblems)
