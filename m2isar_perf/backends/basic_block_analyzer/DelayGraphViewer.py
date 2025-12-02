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

import graphviz
import pathlib
import os

from backends.common import dirUtils as dir_utils

class DelayGraphViewer:

    def __init__(self):        
        self.enforce_input_order  = False
        self.enforce_output_order = False
        self.enforce_inputs_on_same_level  = False
        self.enforce_outputs_on_same_level = False
        self._input_node_style  = {"style":'filled', "fillcolor":'lightyellow'}
        self._output_node_style = {"style":'filled', "fillcolor":'lightblue'}
        self._alias_node_style  = {"style":'filled', "fillcolor":'lightgray'}

        self._temp_dir = pathlib.Path(__file__).parent / "temp"

    def execute(self, delay_grah, out_dir):

        print()
        print("-- BACKEND: DELAY_GRAPH_VIEWER --")

        for variant_name in delay_grah:
            variant = delay_grah[variant_name]

            # Make sure output directories and temp directory exist
            print(f" > Creating output directories for '{variant_name}'")
            temp_dir = self._temp_dir / variant_name
            dir_utils.createOrReplaceDir(temp_dir, suppress_warning=True)
            out_dir = out_dir / variant_name / "doc_delay"

            # Generate sub-dirs for each basic block function
            for block_name in variant:
                assert block_name
                (out_dir / block_name).mkdir(parents=True, exist_ok=True)

                dot_graph = graphviz.Digraph(comment=block_name)
                dot_graph.attr(rankdir='TB')

                outputs = variant[block_name]

                output_names = [n for n in outputs]
                alias_names  = set(var.name for o in output_names for var in outputs[o] if var.name.startswith("o_"))
                input_names  = set(var.name for o in output_names for var in outputs[o] if var.name not in alias_names)
                output_names = sorted(list(output_names))
                input_names  = sorted(list(input_names))
                
                # create input nodes
                with dot_graph.subgraph() as subgraph:
                    if self.enforce_inputs_on_same_level:
                        subgraph.attr(rank='min')
                    prev_node = None
                    for input_var in input_names:
                        node_name = self.__input(input_var)
                        node = subgraph.node(node_name, label=input_var, shape='box', **self._input_node_style)
                        if self.enforce_input_order and prev_node is not None:
                            subgraph.edge(prev_node, node_name, style='invis')
                        prev_node = node_name

                # create output nodes
                with dot_graph.subgraph() as subgraph:
                    if self.enforce_outputs_on_same_level:
                        subgraph.attr(rank='max')
                    prev_node = None
                    for output_var in output_names:
                        node_name = self.__output(output_var)
                        node = subgraph.node(node_name, label=output_var.replace("o_", ""), shape='box', **self._output_node_style)
                        if self.enforce_output_order and prev_node is not None:
                            subgraph.edge(prev_node, node_name, style='invis')
                        prev_node = node_name

                subgraph = dot_graph

                # create all plus nodes originating from input nodes
                for input_var in input_names:
                    self.__generate_out_edges(subgraph, input_var, self.__input, output_names, outputs, **self._input_node_style)

                # create alias nodes (max nodes) and create all plus nodes originating from alias nodes
                for alias_var in alias_names:
                    node_name = self.__max(alias_var)
                    node = subgraph.node(node_name, label="max", shape='ellipse', **self._alias_node_style)
                    self.__generate_out_edges(subgraph, alias_var, self.__max, output_names, outputs, **self._alias_node_style)

                # connect outputs
                for output_var in output_names:
                    node_name = self.__max(output_var)
                    function  = outputs[output_var]
                    if output_var not in alias_names:
                        # if output is made up of multiple edges -> create max node
                        if len(function) > 1:
                            node = subgraph.node(node_name, label="max", shape='ellipse', **self._output_node_style)
                            subgraph.edge(node_name, self.__output(output_var))
                        # else forward to output node
                        else:
                            node_name = self.__output(output_var)
                    else:
                        # create edge from max node to output node
                        subgraph.edge(node_name, self.__output(output_var))
                    edges = {}
                    for var in function:
                        if var.delay == 0:
                            # if zero is no added delay refer to the correspoding source node
                            if var.name in alias_names:
                                subgraph.edge(self.__max(var.name), node_name)
                            else:
                                subgraph.edge(self.__input(var.name), node_name)
                            continue
                        # avoid duplicate edges
                        if not var.name in edges:
                            edges[var.name] = []
                        elif var.delay in edges[var.name]:
                            continue
                        # create edge between plus node and output node
                        subgraph.edge(self.__plus(var.name, var.delay), node_name)
                        edges[var.name].append(var.delay)

                temp_file = temp_dir / f"{block_name}.dot"
                with temp_file.open('w') as f:
                    f.write(dot_graph.source)

                os.chdir(temp_dir)
                os.system(f"dot -Tpdf {block_name}.dot -o {block_name}.pdf")
                os.replace(f"{str(temp_dir)}/{block_name}.pdf", f"{str(out_dir / block_name)}/{block_name}_delay_graph.pdf")

    def __generate_out_edges(self, subgraph, var_name, func, output_names, outputs, **kwargs):
        edges = []
        for output in output_names:
            for var in outputs[output]:
                if var.name != var_name:
                    continue
                if var.delay == 0:
                    continue
                # avoid duplicate edges
                if var.delay in edges:
                    continue
                node_name = self.__plus(var.name, var.delay)
                node = subgraph.node(node_name, label=f"+{var.delay}", shape='ellipse', **kwargs)
                #nodes[node_name] = node
                subgraph.edge(func(var.name), node_name)
                edges.append(var.delay)

    def __input(self, name):
        return ("in_" + name)

    def __output(self, name):
        return name #("out_" + name)

    def __plus(self, name, value):
        return f"plus_{value}_{name}"

    def __max(self, function):
        return ("max_" + function) #f"{function}".replace(" + ", "_").replace(",", "_").replace(" ", "").replace("[", "").replace("]", ""))