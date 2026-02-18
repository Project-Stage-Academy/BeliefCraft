update_descriptions_prompt = '''
There is a book containing Julia code with accompanying explanatory text. The code has already been translated into Python. Your task is to:
1. Replace the Julia code with the corresponding Python code.
2. Update the description so that it naturally matches the Python code, as if it had originally been written for Python.
3. Do not mention translation or Julia in the updated text.

Important constraints:
- Modify only the parts of the description that directly refer to the Julia code.
- Leave everything else unchanged, even if references appear incomplete or out of context.
- Preserve all variable names.
- If variables use Greek letters, transliterate them into English.
- Do not modify mathematical formulas, even if they resemble code.
- If “Appendix G” is mentioned (it contains Julia instructions), remove that reference.
- If a fragment defines a method of a class declared elsewhere in the book, wrap the method inside a minimal class definition:
```python
class ClassName:
    # ...
    def method_name(...):
        ...
```
- Additional helper functions may be provided in the prompt for context (including their full source code). These functions already exist elsewhere in the book and must NOT be duplicated in the translated code unless they are explicitly part of the original fragment being replaced.

Input:
Original Julia fragments with descriptions:

{}

Available Python code to use:

{}

Output format (JSON array):
[
    {{
        "algorithm_number": "Algorithm X.X.",
        "description": "...",
        "code": "...",
        "declarations": {{
            "original_julia_declaration": "corresponding_python_declaration",
        }}
    }},
    ...
]

In the "declarations" field:
- Include only top-level function and struct definitions.
- Exclude variable assignments and type annotations.
- Keys must be the original Julia declarations.
- Values must be the corresponding Python declarations.
- For methods, use the format: "ClassName.method_name".
'''

translate_python_code_prompt = '''
You are working on a book that contains code blocks with explanatory text. Some earlier blocks have already been rewritten into Python and the book text was updated accordingly. Now you must do the same for the new blocks provided below.

Your task is to:
1. Translate the Julia code fragment into idiomatic Python.
2. Update the description so that it naturally matches the Python code, as if it had originally been written for Python.
3. Do not mention translation, Julia, or that anything was rewritten.

Important constraints:
- Modify only the parts of the description that directly refer to code details (data structures, indexing ranges, library names, function names, return values, etc.).
- Leave everything else unchanged, even if references appear incomplete or out of context.
- Preserve all variable names exactly.
- If variables use Greek letters, transliterate them into English (e.g., ϕ → phi).
- Do not modify mathematical formulas, even if they resemble code.
- If “Appendix G” is mentioned, remove that reference (it contains language-specific instructions).
- Do not duplicate helper functions/classes that are stated as already existing in the book; only output what belongs to the original fragment you are replacing.
- Many chapters define a struct first, and later define functions that conceptually belong to that struct. In Python, treat:
    - struct Name ... end as class Name: ...
    - functions whose first argument is that struct type (e.g., f(x::Name, ...)) as methods on that class (e.g., Name.f(self, ...)), preserving variable names.

If a fragment defines a method of a class declared elsewhere in the book, wrap the method inside a minimal class definition:
class ClassName:
    # ...
    def method_name(...):
        ...

Inferring design conventions from already-translated code:
Before writing any code, carefully read all "Available Python code" provided. Identify and strictly follow every design pattern already established: inheritance hierarchies, whether functions are free or methods, naming conventions, utility methods on classes, and library choices for randomness or linear algebra. When in doubt, always prefer consistency with the existing code over a locally cleaner solution.

Modeling Julia multiple dispatch:
When a Julia function uses multiple dispatch on a type (e.g., infer(M::ExactInference, ...)), always translate this as a method on that class (e.g., ExactInference.infer(self, ...)), never as a global function with isinstance checks. If such methods share a common role across several classes, introduce a common base class (e.g., class ExactInference(InferenceMethod):), even if that base class is not visible in the available code.

Output format (JSON array):
[
{{
"algorithm_number": "Algorithm X.X.",
"description": "...",
"code": "...",
"declarations": {{
"original_julia_declaration": "corresponding_python_declaration"
}}
}},
...
]

In the "declarations" field:
- Include only top-level function and struct definitions.
- Exclude variable assignments and type annotations.
- Keys must be the original Julia declarations.
- Values must be the corresponding Python declarations.
- For methods, use the format: "ClassName.method_name".

GOLDEN EXAMPLE (already completed earlier in the book)
Use this as the reference for style, struct→class mapping, and function→method mapping.

Original Julia fragments with descriptions:

Algorithm 2.1. Types and functions relevant to working with factors over a set of discrete variables. A variable is given a name (represented as a symbol) and may take on an integer from 1 to m. An assignment is a mapping from variable names to values represented as integers. A factor is defined by a factor table, which assigns values to different assignments involving a set of variables and is a mapping from assignments to real values. This mapping is represented by a dictionary. Any assignments not contained in the dictionary are set to 0. Also included in this algorithm block are some utility functions for returning the variable names associated with a factor, selecting a subset of an assignment, enumerating possible assignments, and normalizing factors. As discussed in appendix G.3.3, product produces the Cartesian product of a set of collections. It is imported from Base.Iterators.

struct Variable
name::Symbol
r::Int # number of possible values
end
const Assignment = Dict{{Symbol,Int}}
const FactorTable = Dict{{Assignment,Float64}}
struct Factor
vars::Vector{{Variable}}
table::FactorTable
end
variablenames(ϕ::Factor) = [var.name for var in ϕ.vars]
select(a::Assignment, varnames::Vector{{Symbol}}) =
Assignment(n=>a[n] for n in varnames)
function assignments(vars::AbstractVector{{Variable}})
names = [var.name for var in vars]
return vec([Assignment(n=>v for (n,v) in zip(names, values))
for values in product((1:v.r for v in vars)...)])
end
function normalize!(ϕ::Factor)
z = sum(p for (a,p) in ϕ.table)
for (a,p) in ϕ.table
ϕ.table[a] = p/z
end
return ϕ
end

Algorithm 2.2. A discrete Bayesian network representation in terms of a set of variables, factors, and a graph. The graph data structure is provided by Graphs. jl.

struct BayesianNetwork
vars::Vector{{Variable}}
factors::Vector{{Factor}}
graph::SimpleDiGraph{{Int64}}
end

Algorithm 2.3. A function for evaluating the probability of an assignment given a Bayesian network bn. For example, if bn is as defined in example 2.5, then $ a = (b=1, s=1, e=1, d=2, c=1) $ probability(bn, Assignment(a)) returns 0.03422865599999999.

function probability(bn::BayesianNetwork, assignment)
subassignment(ϕ) = select(assignment, variablenames(ϕ))
probability(ϕ) = get(ϕ.table, subassignment(ϕ), 0.0)
return prod(probability(ϕ) for ϕ in bn.factors)
end

Translated and updated version (reference output):

[
{{
"algorithm_number": "Algorithm 2.1.",
"description": "Types and functions relevant to working with factors over a set of discrete variables. A variable is given a name (represented as a string) and may take on an integer from 0 to r - 1. An assignment is a mapping from variable names to integer values. A factor is defined by a factor table, which assigns values to different assignments involving a set of variables and is a mapping from assignments to real values. This mapping is represented by a dictionary. Any assignments not contained in the dictionary are set to 0. Also included in this algorithm block are some utility functions for returning the variable names associated with a factor, selecting a subset of an assignment, enumerating possible assignments, and normalizing factors. itertools.product produces the Cartesian product of a set of collections.",
"code": "class Variable():\n def init(self, name: str, r: int):\n self.name = name\n self.r = r # number of possible values\n\n\nclass Assignment(dict[str, int]):\n def select(self, varnames: list[str]) -> 'Assignment':\n return Assignment({{n: dict.getitem(self, n) for n in varnames}})\n\n def hash(self) -> int:\n return hash(tuple(sorted(self.items())))\n\n def copy(self) -> 'Assignment':\n result = Assignment()\n result.update(self)\n return result\n\n\nclass FactorTable(dict[Assignment, float]):\n def get(self, key: Assignment, default_val: float):\n return dict.getitem(self, key) if key in self.keys() else default_val\n\n\nclass Factor():\n def init(self, variables: list[Variable], table: FactorTable):\n self.variables = variables\n self.table = table\n self.variable_names = [var.name for var in variables]\n\n def normalize(self):\n z = np.sum([self.table[a] for a in self.table])\n for a, p in self.table.items():\n self.table[a] = p/z\n\n\ndef assignments(variables: list[Variable]) -> list[Assignment]:\n names = [var.name for var in variables]\n return [Assignment(zip(names, values)) for values in itertools.product(*[[i for i in range(var.r)] for var in variables])]",
"declarations": {{
"struct Variable": "Variable",
"struct Factor": "Factor",
"variablenames(ϕ::Factor)": "Factor.variable_names",
"select(a::Assignment, varnames::Vector{{Symbol}})": "Assignment.select",
"function assignments(vars::AbstractVector{{Variable}})": "assignments",
"function normalize!(ϕ::Factor)": "Factor.normalize"
}}
}},
{{
"algorithm_number": "Algorithm 2.2.",
"description": "A discrete Bayesian network representation in terms of a set of variables, factors, and a graph. The graph data structure is provided by networkx.",
"code": "class BayesianNetwork():\n def init(self, variables: list[Variable], factors: list[Factor], graph: nx.DiGraph):\n self.variables = variables\n self.factors = factors\n self.graph = graph",
"declarations": {{
"struct BayesianNetwork": "BayesianNetwork"
}}
}},
{{
"algorithm_number": "Algorithm 2.3.",
"description": "A method for evaluating the probability of an assignment given a Bayesian network bn. For example, if bn is as defined in example 2.5, then $ a = (b=1, s=1, e=1, d=2, c=1) $ bn.probability(Assignment(a)) returns 0.03422865599999999.",
"code": "class BayesianNetwork:\n # other methods are defined elsewhere\n def probability(self, assignment: Assignment) -> float:\n def subassignment(phi): return assignment.select(phi.variable_names)\n def prob(phi): return phi.table.get(subassignment(phi), default_val=0.0)\n return np.prod([prob(phi) for phi in self.factors])",
"declarations": {{
"function probability(bn::BayesianNetwork, assignment)": "BayesianNetwork.probability"
}}
}}
]

NOW DO THE NEW WORK

Input:
Original Julia fragments with descriptions:
{}

Available Python code to use (already exists elsewhere in the book; do NOT duplicate unless it is explicitly part of the fragment being replaced):
{}

Return only the JSON array in the required format.
'''


translate_example_prompt = '''
You are working on a book that contains examples combining explanatory text and code. Earlier parts of the book have already been rewritten so that all code is in Python and the surrounding text has been updated accordingly.

Your task is to:
1. Rewrite the code fragment in Python, using the already-defined Python classes and functions provided in the context.
2. Update the surrounding text so that it naturally matches the Python code, as if the example had originally been written for Python.
3. Do not mention translation, Julia, or that anything was rewritten.

Important constraints:
- Modify only the parts of the text that directly refer to code-level details (syntax, constructors, indexing conventions, libraries, helper utilities, etc.).
- Leave all conceptual explanations unchanged, even if they appear informal, incomplete, or narrative.
- Preserve all variable names exactly.
- If variables use Greek letters, transliterate them into English.
- Do not modify mathematical formulas, even if they resemble code.
- If “Appendix G” or appendix-specific convenience functions are mentioned, remove those references.
- Do not introduce new classes, functions, or data structures.
- Assume that all referenced classes and functions already exist in Python and have been defined earlier in the book.

Output format (JSON array):
[
  {{
    "example_number": "Example X.X.",
    "description": "...",
    "text": "..."
  }}
]

Input:
Examples with text and Julia code:
{}

Available Python code to use (already defined elsewhere in the book):
{}

Return only the JSON array in the required format.
'''
