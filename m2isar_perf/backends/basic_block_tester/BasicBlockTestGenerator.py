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

import copy
from collections import deque
from typing import List, Dict
from backends.common import dirUtils
from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, StaticEdge
from meta_models.block_scheduling_model.BlockSchedulingTransformer import BasicBlockDescription

class BasicBlockTestGenerator:

    def __init__(self):
        pass

    def execute(self, sched_model:SchedulingModel, block_model:SchedulingModel, basic_blocks:List[BasicBlockDescription], out_dir):
        self.out_dir = out_dir
        
        print()
        print("-- BACKEND: BASIC_BLOCK_TEST_GENERATOR --")

        idx = 0
        for variant_i in sched_model.getAllVariants():
            block_variant_i = block_model.getAllVariants()[idx]
            idx += 1

            print(f" > Creating output directory for {variant_i.name}")
            out_dir = self.out_dir / variant_i.name / "bb_test"
            dirUtils.createOrReplaceDir(out_dir)
            
            for basic_block in basic_blocks:
                self.__generateTestsForBaseModel(variant_i, basic_block, out_dir / "instr_sched_model.py")
                self.__generateTestsForBlockModel(block_variant_i, basic_block, out_dir / "block_sched_model.py")

            self.__generateMain(basic_blocks, out_dir / "main.py")

    def __generateTestsForBaseModel(self, variant, basicBlock, outFile):
                
        schedFuncDict = { schedFunc_i.name: schedFunc_i for schedFunc_i in variant.getAllSchedulingFunctions() }

        #####

        code = ""
        inputs = [ timing_var.name for timing_var in variant.getAllTimingVariables() ]
        outputs = copy.deepcopy(inputs)

        numInstr = len(basicBlock.instructions)
        for i, instr_i in enumerate(basicBlock.instructions):
            isFirstInstr = (i == 0)
            isLastInstr  = (i == numInstr - 1)

            schedFunc = schedFuncDict[instr_i.name]

            visitedNodes = []
            nodeQueue = deque([schedFunc.getRootNode()])

            code += "\n"
            code += f"\t# {hex(instr_i.address)}, {instr_i.name} \n"

            while nodeQueue:
                curNode = nodeQueue.popleft()
                if curNode not in visitedNodes:
                    visitedNodes.append(curNode)
                   
                    # Process current node
                    code += f"\tn_{i}_{curNode.name} = "
                    
                    inElements = []
                    for node_i in curNode.getAllInNodes():
                        inElements.append(f"n_{i}_{node_i.name}")
                    for edge_i in curNode.getAllInEdges():
                        if edge_i.isDynamic():
                            if "Pc" not in edge_i.name or isFirstInstr:
                                if edge_i.name == "Xa":
                                    inEdge = f"reg_{instr_i['Xa']}"
                                elif edge_i.name == "Xb":
                                    inEdge = f"reg_{instr_i['Xb']}"
                                else:
                                    inEdge = f"in_{i}_{edge_i.name}"

                                if inEdge not in inputs and inEdge not in outputs:
                                    inputs.append(inEdge)
                                inElements.append(inEdge)
                        else: # Static edge
                            inElements.append(f"{edge_i.getTimingVariable().name}")

                    if len(inElements) > 1:
                        code += "max(["
                        code += ", ".join(inElements)
                        code += "])"
                    elif len(inElements) == 1:
                        code += inElements[0]
                    
                    if not curNode.hasZeroDelay():
                        if curNode.hasDynamicDelay():
                            edge = f"i_{curNode.getResourceModel().name}"
                            code += f" + {edge}"
                            if edge not in inputs:
                                inputs.append(edge)
                        else:
                            code += f" + {curNode.getDelay()}"

                    code += "\n" 

                    outEdges = []
                    for outEdge_i in curNode.getAllOutEdges():
                        if outEdge_i.isDynamic():
                            if "Pc_" not in outEdge_i.name or isLastInstr:
                                if outEdge_i.name == "Xd":
                                    outEdge = f"reg_{instr_i['Xd']}"
                                else:   
                                    outEdge = f"out_{i}_{outEdge_i.name}"
                                if outEdge not in outputs:
                                    outputs.append(outEdge)
                                outEdges.append(outEdge)
                        else:
                            outEdges.append(outEdge_i.getTimingVariable().name)
                    for outEdge_i in outEdges:
                        code += f"\t{outEdge_i} = n_{i}_{curNode.name}\n"
                        

                    # Add children to queue
                    for nxtNode_i in curNode.getAllOutNodes():
                        if all((predecessor in visitedNodes) for predecessor in nxtNode_i.getAllInNodes()):
                            nodeQueue.append(nxtNode_i)

        basicBlock.__inputs = list(inputs)
        print(inputs, "vs", basicBlock.__inputs)

        function  = f"def {basicBlock.name}(" + ", ".join(inputs) + "):"
        function += code
        function += "\n\treturn {" + ", ".join([ f"'{o}':{o}" for o in outputs]) + "}\n\n"
        print(function)

        with outFile.open('a') as f:
            f.write(function)

    def __generateTestsForBlockModel(self, variant, basicBlock, outFile):
                
        schedFuncDict = { schedFunc_i.name: schedFunc_i for schedFunc_i in variant.getAllSchedulingFunctions() }

        #####

        code = "\n"
        inputs = [ timing_var.name for timing_var in variant.getAllTimingVariables() ]
        outputs = copy.deepcopy(inputs)

        isFirstInstr = True
        isLastInstr  = True

        schedFunc = schedFuncDict[basicBlock.name]

        visitedNodes = []
        nodeQueue = deque([schedFunc.getRootNode()])

        while nodeQueue:
            curNode = nodeQueue.popleft()
            if curNode not in visitedNodes:
                visitedNodes.append(curNode)
                
                # Process current node
                code += f"\tn_{curNode.name} = "
                
                inElements = []
                for node_i in curNode.getAllInNodes():
                    inElements.append(f"n_{node_i.name}")
                for edge_i in curNode.getAllInEdges():
                    if edge_i.isDynamic():
                        print(edge_i.name)
                        if "Xa" in edge_i.name:
                            inEdge = f"reg_{edge_i.name[1:edge_i.name.index(' ')]}"
                        elif "Xb" in edge_i.name:
                            inEdge = f"reg_{edge_i.name[1:edge_i.name.index(' ')]}"
                        elif "Cb_out" in edge_i.name:
                            inEdge = f"in_Cb_out_{edge_i.name[1:edge_i.name.index(' ')]}"
                        else:
                            inEdge = f"in_{edge_i.name}"

                        if inEdge not in inputs:
                            inputs.append(inEdge)
                        inElements.append(inEdge)
                    else: # Static edge
                        inElements.append(f"{edge_i.getTimingVariable().name}")

                if len(inElements) > 1:
                    code += "max(["
                    code += ", ".join(inElements)
                    code += "])"
                elif len(inElements) == 1:
                    code += inElements[0]
                
                if not curNode.hasZeroDelay():
                    if curNode.hasDynamicDelay():
                        edge = f"i_{curNode.getResourceModel().name}"
                        code += f" + {edge}"
                        if edge not in inputs:
                            inputs.append(edge)
                    else:
                        code += f" + {curNode.getDelay()}"

                code += "\n" 

                outEdges = []
                for outEdge_i in curNode.getAllOutEdges():
                    if outEdge_i.isDynamic():
                        if "Xd" in outEdge_i.name:
                            outEdge = f"reg_{outEdge_i.name[1:outEdge_i.name.index(' ')]}"
                        elif "Cb_in" in outEdge_i.name:
                            outEdge = f"out_Cb_in_{outEdge_i.name[1:outEdge_i.name.index(' ')]}"
                        else:   
                            outEdge = f"out_{outEdge_i.name}"
                        if outEdge not in outputs:
                            outputs.append(outEdge)
                        outEdges.append(outEdge)
                    else:
                        outEdges.append(outEdge_i.getTimingVariable().name)
                for outEdge_i in outEdges:
                    code += f"\t{outEdge_i} = n_{curNode.name}\n"
                    

                # Add children to queue
                for nxtNode_i in curNode.getAllOutNodes():
                    if all((predecessor in visitedNodes) for predecessor in nxtNode_i.getAllInNodes()):
                        nodeQueue.append(nxtNode_i)

        if len(inputs) != len(basicBlock.__inputs):
            op("Error:")
            uniqueA = [i for i in basicBlock.__inputs if i not in inputs]
            uniqueB = [i for i in inputs if i not in basicBlock.__inputs]
            op("Not in basic block model:", uniqueA)
            op("Not in instr sched model:", uniqueB)
            raise RuntimeError(f"Inputs mismatch! ({len(basicBlock.__inputs)} vs. {len(inputs)})")

        function  = f"def {basicBlock.name}(" + ", ".join(inputs) + "):"
        function += code
        function += "\n\treturn {" + ", ".join([ f"'{o}':{o}" for o in outputs]) + "}\n\n"
        print(function)

        with outFile.open('a') as f:
            f.write(function)

    def __generateMain(self, basic_blocks, outFile):
        code  = """
from objprint import op
import instr_sched_model as instr_model
import block_sched_model as block_model
"""
        code += "import instr_sched_model as instr_model\n"
        code += "import block_sched_model as block_model\n"
        code += "\n"
        code += "def main():\n"
        for basic_block in basic_blocks:
            code +=  "\tinputs = {\n\t\t" + ',\n\t\t'.join([ f"'{o}' :{' ' * (10 - len(o))}0" for o in basic_block.__inputs ]) + "\n\t}\n"
            code += f"\tprint('Testing {basic_block.name}...')\n"
            code += f"\tA = instr_model.{basic_block.name}(*inputs.values())\n"
            code += f"\tB = block_model.{basic_block.name}(*inputs.values())\n"
            code +=  "\top(A)\n"
            code +=  "\tprint('vs')\n"
            code +=  "\top(B)\n"
            code +=  "\tprint()\n"
            code +=  "\n"
        code += """
if __name__ == "__main__":
    main()
"""

        with outFile.open('w') as f:
            f.write(code)