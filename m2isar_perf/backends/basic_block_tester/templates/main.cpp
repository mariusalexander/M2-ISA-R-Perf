#include <iostream>
#include <cstring>

#include "$$variant_name$$_PerformanceModel.h"
#include "$$variant_name$$_Channel.h"

using namespace $$variant_name$$;
using Model = $$variant_name$$_PerformanceModel;

void setupModel(Channel& channel, Model& model)
{
    model.connectChannel(&channel);

    std::cout << model.getPrintHeader();
}

void executeBasicBlock(Channel& channel, Model& model)
{
    model.newTraceBlock(); // resets instr ptr

    for (int instrIdx = 0; instrIdx < channel.instrCnt; instrIdx++)
    {
        model.callSchedulingFunction(channel.typeId[instrIdx]);
        model.update();
    }
    std::cout << model.getPipelineStream();
    // print non-zero register timing values
    std::cout << "-> registers: ";
    for (int i = 0; i < 64; i++)
    {
        uint64_t reg = model.regModel.get(i);
        if (reg > 0) std::cout << "r" << i << ": " << reg << ", ";
    }
$$multi_timing_variables$$
    std::cout << "\n";
}

int main(int argc, const char *argv[])
{
    $$variant_name$$_Channel channel;
    int32_t iterations = 10;
    int32_t idx = 0;

$$basic_blocks$$
    return 0;
}