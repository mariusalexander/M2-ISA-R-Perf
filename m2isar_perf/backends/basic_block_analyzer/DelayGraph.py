#
# Copyright 2025 Chair of EDA, Technical University of Munich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# TODO: remove me, for debugging purpose only
from objprint import op

import time
import copy
from typing import List, Dict, Optional, TypeAlias
from collections import deque
from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, Edge

class SymbolicVariable:
    """Represents a variable in a max term, associated with an added delay."""

    def __init__(self, name:str, delay:int=0):
        self.name  = name
        self.delay = delay

    def __str__(self):
        return f"{self.delay} + {self.name}"

    def __repr__(self):
        return self.__str__()

    def merge(self, delay:int) -> 'SymbolicVariable':
        return SymbolicVariable(self.name, self.delay + delay)

class MaxTerm(list):
    """Represents a max term, made out of a list of variables."""

    def __init__(self, iterable=None):
        super().__init__(iterable)

    def __str__(self) -> str:
        return f"max({", ".join([str(v) for v in self])})"

    def __repr__(self) -> str:
        return self.__str__()
    
    def __add__(self, value:SymbolicVariable):
        return super().__add__(value)
    
    def __contains__(self, value:str|SymbolicVariable) -> bool:
        if isinstance(value, str):
            assert self.count(v.name == value for v in self) <= 1, f"Duplicate variable '{value}'!"
            return any(v.name == value for v in self)
        assert isinstance(value, SymbolicVariable), f"Incompatible type '{type(value)}'!"
        return value.name in self

    def max_value(self, name:str) -> Optional[int]:
        """
        Returns the maximum added delay of the variable `name`.
        """
        tmp = [v.delay for v in self if v.name == name]
        return max(tmp) if len(tmp) else None

    def names(self) -> List[str]:
        """
        Returns a list of all variable names as they appear in order.
        """
        return list(dict.fromkeys([v.name for v in self])) # fromkeys keeps order

    def expanded(self, intermediates:Dict[str, 'MaxTerm']) -> 'MaxTerm':
        """
        Expands (unrolls) all intermediate variables by their corresponding variables. 
        Returns a new, simplified term.
        """
        expanded = MaxTerm([i.merge(v.delay) for v in self if v.name in intermediates for i in intermediates[v.name]] + \
                           [v                for v in self if v.name not in intermediates])
        assert all([i.name not in intermediates for i in expanded])
        return expanded.simplified()

    def difference(self, other:'MaxTerm') -> 'MaxTerm':
        """
        Returns a new term with only the variables that `other` contains but this term does not.
        Keeps order of names.
        """
        return MaxTerm(filter(lambda v: v.name not in other.names(), self)).simplified()

    def simplified(self) -> 'MaxTerm':
        """
        Minimizes the list of variables. Each variable is listed exactly once.
        Keeps order of names. Returns a new term.
        """
        return MaxTerm([SymbolicVariable(name, self.max_value(name)) for name in self.names()])

    def repacked(self, intermediates:Dict[str, 'MaxTerm']) -> 'MaxTerm':
        """
        Attempts to find a new term, that reuses an intermediate variable to simplify the term.
        Returns a new, simplified, and sorted term.
        """
        expanded   = self.expanded(intermediates)
        best_match = expanded.find_best_intermediate(intermediates, expand=False)
        if best_match is None:
            return expanded # no need to simplify
        repacked = expanded.difference(intermediates[best_match.name])
        repacked.append(best_match)
        return repacked.sorted()

    def sorted(self) -> 'MaxTerm':
        """
        Returns a new term sorted by its delay (descending).
        For variables with same delay, alphabetical order is used.
        """
        return MaxTerm(sorted(self, key=lambda v: (-v.delay, v.name)))
    
    def distance(self, other:'MaxTerm') -> Optional[int]:
        """
        Attempts to find a linear dependency between `self` and `other`.
        For a linear dependency, all variables in `self` must be present in `other` with a consistent offset in their cofactors.
        This offset is called the distance. May return a negative distance, if `self` can be expressed by `other`.
        """
        # self cannot cover other if it has more variables
        if len(self) > len(other):
            return None
        distance = None
        for var in self:
            other_delay = other.max_value(var.name)
            if other_delay is None:
                return None
            # calculate difference
            current = other_delay - var.delay
            # difference in delay is not linear
            if distance is not None and distance != current:
                return None
            distance = current
        return distance

    def find_best_intermediate(self, intermediates:Dict[str, 'MaxTerm'], expand=True, allow_negative_distance=False) -> Optional['SymbolicVariable']:
        """
        Attempts to find an intermediate variable that best covers `self` such that it yields the smallest term.
        `self` must be unrolled to find an intermediate.
        """
        this = self
        if expand: this = self.expanded(intermediates)

        last_name   = None
        last_factor = None
        last_len    = None
        for name in intermediates:
            term   = intermediates[name]
            factor = term.distance(this)
            if factor is None:
                continue
            curr_len = len(term)
            if factor < 0:
                # len must match if distance is negative
                if not allow_negative_distance or curr_len != len(this):
                    continue
            if last_name is not None:
                # prefer if variable covers more variables
                if curr_len < last_len:
                    continue
                # keep last variable if its scores a lower
                if curr_len == last_len and factor > last_factor:
                    continue
                #print(f"INFO: intermediate '{name}' deemed more optimal than '{last_name}'!")
            last_name   = name
            last_factor = factor
            last_len    = curr_len
        if last_name is None:
            return None
        return SymbolicVariable(last_name, last_factor)

class DelayGraphTransformer:
    """Delay Graph"""

    def __init__(self):
        # helper variable to verify that no variable is duplicated
        self._variable_names = {}
        # whether to unroll all delay functions
        self.unroll_delays = False

    def transform(self, block_model:SchedulingModel, unroll_delays=False):
        """
        Transforms a (block) scheduling model into a delay graph.
        For each scheduling function a dict of its outputs and the respective delay functions (max term) is returned.
        Setting `unroll_delays` to `True` will yield a delay graph with a depth of one, i.e. no max terms are shared.
        """
        print("-- BACKENDS: DELAY_GRAPH --")
        self.unroll_delays = unroll_delays
        variants = {}
        # iterate over each variant
        for block_variant in block_model.getAllVariants():
            print(f" > Generating delay graph for '{block_variant.name}'")
            variants[block_variant.name] = self.__generateDelayGraphForEachFunction(block_variant)
            return variants

    def __generateDelayGraphForEachFunction(self, block_variant:Variant):
        block_functions = block_variant.getAllSchedulingFunctions()
        basic_blocks    = {}
        for block_function in block_functions:
            print(f"  > Generating delay graph for '{block_function.name}'")
            start = time.perf_counter_ns()
            basic_blocks[block_function.name] = self.__generateDelayGraphForFunction(block_variant, block_function)
            end   = time.perf_counter_ns()
            print(f"  > took {(end - start) / 1_000_000}ms!")
        return basic_blocks

    def __generateDelayGraphForFunction(self, block_variant:Variant, block_function:SchedulingFunction):
        # max term for each node indexed by its name
        nodes   = {}
        # max term for each output indexed by its name
        outputs = {}
        # variables that are an alias for a max term
        aliases = {}

        self._variable_names = {}

        # find all root nodes
        queue   = deque([n for n in block_function.getAllNodes() if len(n.getAllInNodes()) == 0])
        while queue:
            node = queue.popleft()
            assert node.name not in nodes

            # create max term, discarding redundant variables
            function = self.__get_inputs(node, nodes)
            function = function.repacked(aliases).sorted()

            # store function of current node
            nodes[node.name] = function
            DelayGraphTransformer.print_function(node.name, function, indent=3)

            # set outputs if any
            output_name = self.__set_output(node, outputs, function)

            # create alias if function is a max node (multiple input edges)
            if not self.unroll_delays:
                if output_name is not None and len(function) > 1:
                    self.__update_aliases(node.name, nodes, output_name, outputs, aliases)

            assert not any([v.delay < 0 for v in nodes[node.name]]), f"Term of '{node.name}' contains negative cofactors!"

            # iterate over children if all dependencies have been met
            for next_node_i in node.getAllOutNodes():
                if all((predecessor.name in nodes) for predecessor in next_node_i.getAllInNodes()):
                    queue.append(next_node_i)

        # make sure all nodes have been processed
        assert all([ n.name in nodes for n in block_function.getAllNodes() ])

        print(f"   > outputs:")
        for output in outputs:
            DelayGraphTransformer.print_function(output, outputs[output], indent=4)

        return outputs

    def __get_inputs(self, node:Node, nodes:Dict[str, 'MaxTerm']) -> 'MaxTerm':
        """
        Accumulates all input variables for the given node.
        Returns a non-simplified term.
        """
        term = MaxTerm([])
        # append in edges to function
        for in_edge in node.getAllInEdges():
            name = self.__variable_name(in_edge)
            if name == 'r0':
                continue
            variable = SymbolicVariable(name, node.delay)
            term.append(variable)
        # append in node to function
        for in_node in node.getAllInNodes():
            for variable in nodes[in_node.name]:
                term.append(variable.merge(node.delay))
        # append variable delay of resource model
        if node.resourceModel:
            name = self.__simplify_variable_name(node.name)
            variable = SymbolicVariable(name, node.delay)
            term.append(variable)
        return term

    def __set_output(self, node:Node, outputs:Dict[str, 'MaxTerm'], function:'MaxTerm') -> str:
        """
        Sets the node's function to all outputs of this node.
        Yields the name of the last output that was set (if any)
        """
        alias_name = None
        for edge in node.getAllOutEdges():
            var_name = self.__variable_name(edge, prefix="o_")
            outputs[var_name] = function
            alias_name = var_name
            print(f"     -> sets '{alias_name}'")
        return alias_name

    def __update_aliases(self,
                         node_name:str,
                         nodes:Dict[str, 'MaxTerm'],
                         output_name:str,
                         outputs:Dict[str, 'MaxTerm'],
                         intermediates:Dict[str, 'MaxTerm']):
        """
        Creates an alias for the function of the current node, if no other alias covers this node.
        Otherwise, all references are updated.
        """
        current_term = nodes[node_name]
        expanded = current_term.expanded(intermediates)
        new_term = [SymbolicVariable(output_name)]

        if len(nodes[node_name]) > 1:
            # check if term is covered by other intermediate
            best_match = expanded.find_best_intermediate(intermediates=intermediates, expand=False, allow_negative_distance=True)
            if best_match is not None and best_match.name not in current_term:
                other_term = intermediates[best_match.name]
                if best_match.delay >= 0:
                    print(f"INFO: intermediate '{output_name}' is a multiple of '{best_match.name}'! (distance: {best_match.delay})")
                    # link to other intermediate
                    new_term = MaxTerm([best_match])
                    # add variables not in other term to new term
                    if len(other_term) != len(expanded):
                        extension = expanded.difference(other_term)
                        new_term += extension
                        intermediates[output_name] = expanded
                        print(f"INFO: alias '{output_name}' was extended by '{", ".join([str(v) for v in extension])}'")
                    expanded = new_term
                else:
                    # other alias is a negative multiple of this alias
                    print(f"INFO: intermediate '{best_match.name}' is a negative multiple of '{output_name}'! (distance: {best_match.delay})")
                    assert len(other_term) == len(expanded)
                    new_term = MaxTerm([SymbolicVariable(output_name, -best_match.delay)])
                    # update old output
                    outputs[best_match.name] = new_term
                    del intermediates[best_match.name]
                    # update all references to old alias
                    for n in nodes:
                        for var in nodes[n]:
                            if var.name == best_match.name:
                                print(f"INFO: -> updated '{n}'!")
                                var.name   = output_name
                                var.delay += -best_match.delay
        # save new alias
        intermediates[output_name] = expanded
        # update output of this node to alias
        nodes[node_name]           = new_term

    def __variable_name(self, edge:Edge, prefix:str=""):
        """
        Generates a unique but simplified variable for the given edge.
        """
        var_name = prefix
        if edge.isDynamic():
            var_name += edge.name
        elif edge.timingVariable.getNumElements() == 1:
            var_name += edge.timingVariable.name
        else:
            var_name += f"{edge.timingVariable.name}[{edge.depth}]"
        return self.__simplify_variable_name(var_name)

    def __simplify_variable_name(self, var_name:str):
        """
        Simplifies the variable name but gurantees that the variable is unique.
        """
        new_name =  var_name.lower() \
            .replace(" (xa)", "") \
            .replace(" (xb)", "") \
            .replace(" (xd)", "") \
            .replace(" (cb_out)", "_cb_out") \
            .replace(" (cb_in)", "_cb_in") \
            .replace("_stage", "") \
            .replace("_substage", "_sub") \
            .replace("model", "")
        assert new_name not in self._variable_names or self._variable_names[new_name] == var_name, \
               f"generated duplicate variable name! ('{new_name}' from '{var_name}' clashes with '{self._variable_names[new_name]}')"
        self._variable_names[new_name] = var_name
        return new_name

    @staticmethod
    def function_to_str(function:'MaxTerm', indent=0, word_wrap_at=150):
        """
        Generates a nicely readable function.
        """
        return str(function)

        text = str(function)[1:-1] # remove brackets
        lines = []
        while len(text) > word_wrap_at:
            try:
                idx  = text.index(", ", word_wrap_at)
                idx += 2
            except ValueError:
                break
            lines += [text[:idx]]
            text   = text[idx:]
        lines += [text]
        return f"\n{" " * (indent)}".join(lines)

    @staticmethod
    def print_function(name:str, function:'MaxTerm', indent=0):
        """
        Prints the node and its function in a standardized manner. Used for stdout
        """
        function_str = DelayGraphTransformer.function_to_str(function, indent=20 + 9)
        print(f"{" " * indent}> {name.ljust(20 - indent)} = {function_str}")