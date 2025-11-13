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

from objprint import op

import copy
from typing import List, Dict
from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node

# wrapper to support dot-notation (see https://stackoverflow.com/questions/2352181/how-to-use-a-dot-to-access-members-of-dictionary)
class dotdict(dict):
    """Allows 'dot.notation' access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

class BasicBlockDescription:
    """Denotes a basic block and its instructions."""

    def __init__(self, name, starting_address=0x0):
        self.name = name
        self.starting_address = starting_address
        self.instructions = []

    def addInstruction(self, instr_name, rd=None, rs1=None, rs2=None, imm=None):
        instr = {
            "address": self.starting_address + 4*len(self.instructions),
            "name": instr_name,
            "rd"  : rd, 
            "rs1" : rs1,
            "rs2" : rs2,
            "imm" : imm,
            # RV32 specific
            "Xd"  : rd, 
            "Xa"  : rs1, 
            "Xb"  : rs2,
        }
        self.instructions.append(dotdict(instr))

class BlockSchedulingTransformer:
    """Block Scheduling Transformer"""

    def __init__(self):
        self.id_=1024

    def transform(self, sched_model:SchedulingModel, block_descriptions:List[BasicBlockDescription]) -> SchedulingModel:
        """
        Transforms basic blocks (BB) into a block scheudling model. 
        The model is a regular Scheduling Model which only contains scheduling function that describe each BB instead.
        """
        print ("-- TRANSMFORMER: BLOCK_SCHEDULING_MODEL --")

        blockSchedulingModel = SchedulingModel()

        # iterate over each variant
        for sched_variant in sched_model.getAllVariants():
            print(f"> Generating block scheduling model for {sched_variant.name}")

            block_variant = blockSchedulingModel.createVariant(sched_variant.name)

            # TODO: can we simply copy timing variables and external models?
            block_variant.timingVariables = copy.deepcopy(sched_variant.timingVariables)
            block_variant.externalModels  = copy.deepcopy(sched_variant.externalModels)

            # iterate over each BB
            for block_desc in block_descriptions:
                self.__generateBlockSchedulingFunction(sched_variant, block_variant, block_desc)

        return blockSchedulingModel

    def __generateBlockSchedulingFunction(self, sched_variant:Variant, block_variant:Variant, block_desc:BasicBlockDescription):
        """ 
        """
        print(f" > Generating block scheduling function for '{block_desc.name}'...")

        block_function = block_variant.createSchedulingFunction(block_desc.name, self.id_)
        self.id_ += 1

        # iterate over each instruction in BB
        for block_idx in range(0, len(block_desc.instructions)):
            block_instr = block_desc.instructions[block_idx]
            print(f"  > Appending instruction '{block_instr.name}'...")

            # find instruction of BB in base scheduling model and append nodes to block function
            sched_functions = sched_variant.getAllSchedulingFunctions()
            sched_function = self.__findSchedulingFunctionByName(sched_functions, block_instr.name)
            self.__appendSchedulingFunction(sched_function, block_variant, block_function, block_idx)
            
        # Note: These can easily be merged, reducing times we loop over all nodes at cost of less readible code   
        self.__resolveTimingVariables(block_variant, block_function)
        self.__resolveRegisters(block_variant, block_function, block_desc)
        self.__resolveBranchPrediction(block_variant, block_function, block_desc)
        # TODO: resolve "Enter" nodes
            
    def __appendSchedulingFunction(self, sched_function:SchedulingFunction, block_variant:Variant, block_function:SchedulingFunction, block_idx:int):
        """ 
        Appends all nodes of `sched_function` to `block_function`.
        All Properties of each node are copied over.
        """
        # add all nodes of instruction to block schedule
        for source_node in sched_function.nodes:
            block_node = block_function.createNode(f"{source_node.name}_{block_idx}")
            # apply properties
            self.__copyNode(source_node, block_node)

        # TODO: do we need to append nodes first?
        # setup in/out-nodes for each node of the instruction
        for source_node in sched_function.nodes:
            block_node = self.__findNode(block_function, block_idx, source_node)
            for source_dependency in source_node.inNodes:
                dependency = self.__findNode(block_function, block_idx, source_dependency)
                dependency.connectNode(block_node)
                
    def __resolveTimingVariables(self, block_variant:Variant, block_function:SchedulingFunction):
        """
        Resolves nodes with static edges to timing variables.
        Nodes of consecutive instructions are interconnected in such a way that a node A writing to a timing variable
        is connected to a node B of another instruction. Only the nodes that first access and last write to a timing variable
        reatin ingoing and outgoing edges to the corresponding timing variables.    
        """
        print("  > Resolving timing variables...")

        # dict denoting which node last wrote to a timing variable
        timing_variable_mappings = { var:[] for var in block_variant.timingVariables.keys()}

        # iterate over all nodes in order
        for block_node in block_function.nodes:
            instr_idx = self.__getInstructionIndexOfNode(block_node)

            # find in- and out-edges to timing variables
            in_timing_vars_to_resolve  = [ edge for edge in block_node.inEdges  if not edge.dynamic and edge.timingVariable ]
            out_timing_vars_to_resolve = [ edge for edge in block_node.outEdges if not edge.dynamic and edge.timingVariable ]

            # keep rest if in- and out-edges
            block_node.inEdges  = [ edge for edge in block_node.inEdges  if edge not in in_timing_vars_to_resolve  ]
            block_node.outEdges = [ edge for edge in block_node.outEdges if edge not in out_timing_vars_to_resolve ]

            for edge in in_timing_vars_to_resolve:
                # find node that matches depth
                last_node = None
                timing_variable = edge.timingVariable.name
                #op(timing_variable_mappings, attr_pattern=r"(name|depth)", exclude=["inNodes", "outNodes", ""])
                for [idx, node] in timing_variable_mappings[timing_variable]:
                    if idx > (instr_idx - edge.depth):
                        break
                    last_node = node
                # connect to input timing variable if no other node with sufficient depth wrote to it
                if not last_node:
                    print (f"   > Resolved timing variable: Node '{block_node.name}' links to '{timing_variable}'")
                    block_node.inEdges.append(edge) # reappend edge
                    continue
                # connect to node with sufficient depth that wrote last to the timing variable
                print (f"   > Resolved timing variable: Node '{block_node.name}' links to '{block_node.name}' ({timing_variable})")
                last_node.connectNode(block_node)

            # update last node that wrote to timing variables 
            for edge in out_timing_vars_to_resolve:
                print (f"   > Resolved timing variable: Node '{block_node.name}' sets '{timing_variable}'")
                timing_variable_mappings[edge.timingVariable.name].append((instr_idx, block_node))

        # connect timing variable outputs 
        for timing_variable in timing_variable_mappings:
            mappings = timing_variable_mappings[timing_variable]
            if not len(mappings):
                continue
            [_, block_node] = mappings[-1]
            if block_node:
                print (f"   > Resolved timing variable: Node '{block_node.name}' outputs '{timing_variable}'")
                block_node.createStaticOutEdge(timing_variable)

    def __resolveRegisters(self, block_variant:Variant, block_function:SchedulingFunction, block_desc:BasicBlockDescription):
        """
        Resolves nodes with dynamic edges to registers.
        Nodes of consecutive instructions are interconnected in such a way that a node A writing to a register
        is connected to a node B of another instruction that uses the same register as an input. Only the nodes 
        that first read or write last to a register retain the corresponding ingoing and outgoing edges to the register model. """
        print("  > Resolving registers...")

        register_mapping = { reg:None for reg in range(0, 32)}
        # TODO: resolve dynamically
        target_register_name = 'Xd'
        
        for block_node in block_function.nodes:
            instr_index = self.__getInstructionIndexOfNode(block_node)
            instr = block_desc.instructions[instr_index]

            # find in- and out-edges to registers
            # TODO: resolve hardcoded 'regModel' name dynamically
            in_registers_to_resolve  = [ edge for edge in block_node.inEdges  if edge.dynamic and edge.connectorModel.name == 'regModel' ]
            out_registers_to_resolve = [ edge for edge in block_node.outEdges if edge.dynamic and edge.connectorModel.name == 'regModel' ]

            # keep rest if in- and out-edges
            block_node.inEdges  = [ edge for edge in block_node.inEdges  if edge not in in_registers_to_resolve  ]
            block_node.outEdges = [ edge for edge in block_node.outEdges if edge not in out_registers_to_resolve ]

            for edge in in_registers_to_resolve:
                # find register number by name (e.g. rs1 -> r12)
                register = instr[edge.name]
                last_node = register_mapping[register]
                # connect node to register if no other node wrote to it
                if not last_node:
                    print (f"   > Resolved register: Node '{block_node.name}' uses 'r{register} ({edge.name})' from the register model")
                    edge.name = f"r{register} ({edge.name})"
                    block_node.inEdges.append(edge) # reappend edge
                    continue
                # connect node to last node that wrote to register
                print (f"   > Resolved register: Node '{block_node.name}' uses 'r{register} ({edge.name})' set by '{last_node.name}'")
                last_node.connectNode(block_node)

            for edge in out_registers_to_resolve:
                register = instr[edge.name]
                print (f"   > Resolved register: Node '{block_node.name}' sets 'r{register} ({edge.name})'")
                register_mapping[register] = block_node
        
        # connect register outputs 
        for register in register_mapping:
            # TODO: no need to write r0 in RISC-V
            block_node = register_mapping[register]
            if block_node:
                print (f"   > Resolved register: Node '{block_node.name}' outputs 'r{register} ({target_register_name})'")
                block_node.createDynamicOutEdge(f"r{register} ({target_register_name})", "regModel")

    def __resolveBranchPrediction(self, block_variant:Variant, block_function:SchedulingFunction, block_desc:BasicBlockDescription):
        """ 
        Resolves nodes with edges to branch prediction connector models. 
        Only the first instruction retains ingoing edges and the last instruction contains outgoing edges 
        to branch prediction connector models.
        """
        print("  > Resolving branch prediciton...")

        for block_node in block_function.nodes:
            instr_index = self.__getInstructionIndexOfNode(block_node)

            # TODO: is it sufficient to consider only first and last instruction?
            # only keep edges if its either the first or last instruction
            if instr_index != 0:
                in_bp_to_resolve   = [ edge for edge in block_node.inEdges  if edge.dynamic and  "BranchPredModel" in edge.connectorModel.name ]
                block_node.inEdges = [ edge for edge in block_node.inEdges  if edge not in in_bp_to_resolve ]
            if instr_index != len(block_desc.instructions) - 1:
                out_bp_to_resolve   = [ edge for edge in block_node.outEdges if edge.dynamic and "BranchPredModel" in edge.connectorModel.name ]
                block_node.outEdges = [ edge for edge in block_node.outEdges if edge not in out_bp_to_resolve ]

    def __getInstructionIndexOfNode(self, node) -> int:
        return int(node.name[node.name.rindex("_") + 1:])

    def __findElementByName(self, elements, name, error_str = ""):
        element = list(filter(lambda e: e.name == name, elements))
        assert len(element) == 1, error_str
        return element[0]

    def __findSchedulingFunctionByName(self, elements, instr_name) -> SchedulingFunction :
        return self.__findElementByName(elements, instr_name, f"BlockSchedulingTransformer: No scheduling instructions found for instruction '{instr_name}'")
    
    def __findNode(self, block_function:SchedulingFunction, block_idx:int, source_node:Node) -> Node :
        return self.__findElementByName(block_function.nodes, f"{source_node.name}_{block_idx}")
    
    def __copyNode(self, source_node:Node, block_node:Node):
        # apply delay
        block_node.delay = source_node.delay
        # link resource model
        if source_node.resourceModel:
            block_node.resourceModel = block_node.parentVariant.getResourceModel(source_node.resourceModel.name)
        # copy edges
        for in_edge in source_node.getAllInEdges():
            if in_edge.isDynamic():
                block_node.createDynamicInEdge(in_edge.name, in_edge.connectorModel.name)
            else:
                block_node.createStaticInEdge(in_edge.timingVariable.name, in_edge.depth)
        for out_edge in source_node.getAllOutEdges():
            if out_edge.isDynamic():
                block_node.createDynamicOutEdge(out_edge.name, out_edge.connectorModel.name)
            else:
                block_node.createStaticOutEdge(out_edge.timingVariable.name)
