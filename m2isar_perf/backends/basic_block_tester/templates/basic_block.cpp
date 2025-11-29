    ///////////// $$block_desc$$
    {
        $$instr_begin$$
        std::memset(&channel, 0xff, sizeof(channel));
        uint64_t pc  = $$start_address$$;
        idx = 0;

        channel.instrCnt = $$instruction_count$$;
$$instr_channel_setup$$
        Model model1;
        setupModel(channel, model1);

        for (int i = 0; i < iterations; i++)
            executeBasicBlock(channel, model1);


        std::cout << "\n";


        std::memset(&channel, 0xff, sizeof(channel));
        pc  = $$start_address$$;
        idx = 0;

        channel.instrCnt = 1;
$$block_channel_setup$$
        Model model2;
        setupModel(channel, model2);

        for (int i = 0; i < iterations; i++)
            executeBasicBlock(channel, model2);
        $$instr_end$$
    }
    std::cout << "\n\n";