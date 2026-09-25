#!/usr/bin/env python3


from dataclasses import dataclass, field, replace
from typing import Any, Callable, Self
from re import Pattern, compile
from io import TextIOBase
from sys import argv


import operator


String = str
Integer = int


type Parser = Callable[[Span], Node]


@dataclass
class Span:
	buffer: String = field(repr=False)
	path: String = field(default="<buffer>")
	start: Integer = field(default=0)
	end: Integer = field(default=-1)

	def line(self: Self, n: Integer) -> Integer:
		return self.buffer.count("\n", 0, n) + 1

	def column(self: Self, n: Integer):
		line = self.buffer.rfind("\n", 0, n)
		return n - line
	
	def __repr__(self: Self):
		start = f"{self.path}:{self.line(self.start)}:{self.column(self.start)}"
		end = "" if self.end == -1 else f"-{self.line(self.end)}:{self.column(self.end)}"
		return f"{start}{end}"

	def advance(self: Self):
		return replace(self, start=self.end)

	def end_at(self: Self, end: Integer):
		return replace(self, end=end)

	@property
	def view(self: Self):
		return self.buffer[self.start:self.end]


@dataclass
class Node:
	span: Span
	value: Any


class PcError(RuntimeError):
	def __init__(self, span: Span, expected: Any):
		super().__init__(f"{span!r}: Expected {expected!r}, encountered {span.view!r}")


class Pc:
	def __init__(self: Self, fn: Parser):
		self.fn: Parser = fn

	def __call__(self: Self, span: Span | String) -> Node:
		if isinstance(span, String):
			span = Span(span)
		return self.fn(span)

	def __or__(self: Self, other: Self) -> Self:
		return choose(self, other)

	def __add__(self: Self, other: Self) -> Self:
		return sequence(self, other)

	def __getitem__(self: Self, index: Any) -> Self:
		return transform(self, lambda v: v[index])

	def __xor__(self: Self, fn: Callable) -> Self:
		return transform(self, fn)

	def __pos__(self: Self) -> Self:
		return many(self)

	def __inv__(self: Self) -> Self:
		return optional(self)

	def __lshift__(self: Self, other: Other) -> Self:
		return sequence(self, other)[0]

	def __rshift__(self: Self, other: Other) -> Self:
		return sequence(self, other)[1]

	def __matmul__(self: Self, judge: Callable) -> Self:
		return bind(self, judge)

def string(pattern: String) -> Pc:
	def parser(span: Span) -> Node:
		length = len(pattern)
		if span.buffer.startswith(pattern, span.start):
			span = span.end_at(span.start + length)
			return Node(span, pattern)
		raise PcError(span, pattern)

	return Pc(parser)


def re(pattern: String | Pattern) -> Pc:
	if isinstance(pattern, String):
		pattern = compile(pattern)

	def parser(span: Span) -> Node:
		match = pattern.match(span.buffer, span.start)
		if match:
			span = span.end_at(match.end())
			return Node(span, match)
		raise PcError(span, pattern)

	return Pc(parser)


def sequence(*pcs: Pc) -> Pc:
	def parser(span: Span) -> Node:
		results = []
		next = span
		for pc in pcs:
			result = pc(next)
			if isinstance(result.value, list):
				results += result.value
			else:
				results.append(result.value)
			next = result.span.advance()
		span = span.end_at(next.end)
		return Node(span, results)

	return Pc(parser)


def choose(*pcs: Pc) -> Pc:
	def parser(span: Span) -> Node:
		for pc in pcs:
			try:
				return pc(span)
			except PcError:
				continue
		raise PcError(span, f"one of {pcs!r}")

	return Pc(parser)


def transform(pc: Pc, fn: Callable) -> Pc:
	def parser(span: Span) -> Node:
		result = pc(span)
		return replace(result, value=fn(result.value))

	return Pc(parser)


def many(pc: Pc) -> Pc:
	def parser(span: Span) -> Node:
		results = []
		next = span
		result = pc(next)
		results.append(result.value)
		next = result.span.advance()
		while True:
			try:
				result = pc(next)
				results.append(result.value)
			except PcError:
				break
			next = result.span.advance() 
		return Node(span.end_at(next.end), results)

	return Pc(parser) 


def optional(pc: Pc) -> Pc:
	def parser(span: Span) -> Node:
		try:
			return pc(span)
		except PcError:
			return Node(span, pc)
	
	return Pc(parser)


def bind(pc: Pc, judge: Callable) -> Pc:
	def parser(span: Span) -> Node:
		a = pc(span)
		next = judge(a.value)
		b = next(a.span.advance())
		return replace(b, span=replace(b.span, start=span.start))

	return Pc(parser)


def pure(value: Any) -> Pc:
	def parser(span: Span) -> Node:
		return Node(span, value)

	return Pc(parser)


def lazy(get_pc: Callable) -> Pc:
	def parser(span: Span) -> Node:
		try:
			return get_pc()(span)
		except RecursionError:
			raise PcError(span, "get a life nerd")
	
	return Pc(parser)


decimal = re(r"\d+")[0] ^ Integer
space = re(r"\s*")
value = space >> decimal << space
mult = string("*") >> pure(operator.mul) 
div = string("/") >> pure(operator.truediv)
plus = string("+") >> pure(operator.add)
minus = string("-") >> pure(operator.sub)
#apply_binop = lambda v: v[1](v[0], v[2])
apply_binop = lambda v: v
term = ((lazy(lambda: term) + (div | mult) + lazy(lambda: term)) ^ apply_binop) | value
expr = ((lazy(lambda: expr) + (plus | minus) + lazy(lambda: expr)) ^ apply_binop) | term

print(expr(argv[1]))

