package com.codecontextgraph.cobol;

import io.proleap.cobol.asg.metamodel.Program;
import io.proleap.cobol.asg.runner.impl.CobolParserRunnerImpl;
import io.proleap.cobol.preprocessor.CobolPreprocessor.CobolSourceFormatEnum;

import java.io.File;

public class Spike {
    public static void main(String[] args) throws Exception {
        File f = new File(args[0]);
        Program program = new CobolParserRunnerImpl().analyzeFile(f, CobolSourceFormatEnum.FIXED);
        program.getCompilationUnits().forEach(cu -> {
            System.out.println("CU: " + cu.getName());
            System.out.println("  programUnit: " + cu.getProgramUnit());
        });
    }
}
