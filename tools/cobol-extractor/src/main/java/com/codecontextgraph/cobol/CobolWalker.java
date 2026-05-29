package com.codecontextgraph.cobol;

import com.codecontextgraph.cobol.json.EntityJson;
import com.codecontextgraph.cobol.json.FileResultJson;
import com.codecontextgraph.cobol.json.RelationshipJson;
import io.proleap.cobol.asg.metamodel.CompilationUnit;
import io.proleap.cobol.asg.metamodel.Program;
import io.proleap.cobol.asg.metamodel.ProgramUnit;
import io.proleap.cobol.asg.metamodel.call.Call;
import io.proleap.cobol.asg.metamodel.procedure.Paragraph;
import io.proleap.cobol.asg.metamodel.procedure.ProcedureDivision;
import io.proleap.cobol.asg.metamodel.procedure.Statement;
import io.proleap.cobol.asg.metamodel.procedure.perform.PerformProcedureStatement;
import io.proleap.cobol.asg.metamodel.procedure.perform.PerformStatement;
import io.proleap.cobol.asg.params.CobolParserParams;
import io.proleap.cobol.asg.params.impl.CobolParserParamsImpl;
import io.proleap.cobol.asg.runner.impl.CobolParserRunnerImpl;
import io.proleap.cobol.preprocessor.CobolPreprocessor.CobolSourceFormatEnum;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Walks a ProLeap ASG and produces our JSON-contract objects for a single file.
 * v1 scope (this task): Program + Paragraph entities; CONTAINS (program->paragraph)
 * and CALLS (paragraph->paragraph) from PERFORM. Sections, GO TO, CALL and COPY are
 * added in the next task.
 */
public class CobolWalker {
    private final CobolSourceFormatEnum format;
    private final List<File> copybookDirs;

    public CobolWalker(String format, List<File> copybookDirs) {
        this.format = CobolSourceFormatEnum.valueOf(format);
        this.copybookDirs = copybookDirs;
    }

    public FileResultJson walk(File file, String relPath) {
        List<EntityJson> entities = new ArrayList<>();
        List<RelationshipJson> rels = new ArrayList<>();
        try {
            Program program = analyze(file);
            for (CompilationUnit cu : program.getCompilationUnits()) {
                ProgramUnit pu = cu.getProgramUnit();
                if (pu == null || pu.getIdentificationDivision() == null
                        || pu.getIdentificationDivision().getProgramIdParagraph() == null) {
                    continue;
                }
                String progId = pu.getIdentificationDivision()
                        .getProgramIdParagraph().getName().toUpperCase();
                entities.add(new EntityJson("Program", progId, progId, relPath, 1, lineCount(file), false));

                ProcedureDivision pd = pu.getProcedureDivision();
                if (pd == null) continue;
                for (Paragraph para : pd.getParagraphs()) {
                    if (para.getName() == null) continue;
                    String pName = para.getName().toUpperCase();
                    String pQn = progId + "." + pName;
                    // TODO(v2): populate real paragraph line numbers from ProLeap ctx
                    entities.add(new EntityJson("Paragraph", pQn, pName, relPath, 0, 0, false));
                    rels.add(new RelationshipJson(progId, pQn, "CONTAINS", relPath, null, Map.of()));

                    for (Statement stmt : para.getStatements()) {
                        if (stmt instanceof PerformStatement perform) {
                            for (String target : performTargets(perform)) {
                                rels.add(new RelationshipJson(pQn, progId + "." + target,
                                        "CALLS", relPath, null, Map.of("type", "perform")));
                            }
                        } else if (stmt instanceof io.proleap.cobol.asg.metamodel.procedure.call.CallStatement call) {
                            String callee = callTarget(call);
                            if (callee != null) {
                                rels.add(new RelationshipJson(progId, callee, "CALLS",
                                        relPath, null, Map.of("type", "call")));
                            }
                        }
                    }
                }
                addCopyEdges(file, progId, relPath, entities, rels);
            }
            if (entities.stream().noneMatch(e -> e.kind().equals("Program"))) {
                return new FileResultJson(relPath, "error",
                        "no COBOL program found (file did not parse to a program)",
                        List.of(), List.of());
            }
            return new FileResultJson(relPath, "ok", null, entities, rels);
        } catch (Exception e) {
            String msg = e.getClass().getSimpleName()
                    + (e.getMessage() != null ? ": " + e.getMessage() : "");
            return new FileResultJson(relPath, "error", msg, List.of(), List.of());
        }
    }

    private Program analyze(File file) throws Exception {
        if (copybookDirs.isEmpty()) {
            return new CobolParserRunnerImpl().analyzeFile(file, format);
        }
        CobolParserParams params = new CobolParserParamsImpl();
        params.setCopyBookDirectories(copybookDirs);
        params.setCopyBookExtensions(java.util.List.of("", "cpy", "CPY", "cbl", "CBL", "cob", "COB"));
        return new CobolParserRunnerImpl().analyzeFile(file, format, params);
    }

    private static int lineCount(File f) {
        try (var lines = java.nio.file.Files.lines(f.toPath())) {
            return (int) lines.count();
        } catch (Exception e) {
            return 0;
        }
    }

    private static String callTarget(io.proleap.cobol.asg.metamodel.procedure.call.CallStatement call) {
        var vs = call.getProgramValueStmt();
        if (vs == null || vs.getValue() == null) return null;
        String name = vs.getValue().toString().replace("'", "").replace("\"", "").trim();
        return name.isEmpty() ? null : name.toUpperCase();
    }

    private void addCopyEdges(File file, String progId, String relPath,
                              List<EntityJson> entities, List<RelationshipJson> rels) {
        try {
            java.util.Set<String> seen = new java.util.HashSet<>();
            java.util.regex.Pattern pat =
                java.util.regex.Pattern.compile("(?i)\\bCOPY\\s+([A-Z0-9][A-Z0-9-]*)");
            for (String line : java.nio.file.Files.readAllLines(file.toPath())) {
                java.util.regex.Matcher m = pat.matcher(line);
                if (m.find()) {
                    String name = m.group(1).toUpperCase();
                    if (seen.add(name)) {
                        entities.add(new EntityJson("Copybook", name, name, relPath, 0, 0, false));
                        rels.add(new RelationshipJson(progId, name, "IMPORTS", relPath, null, Map.of()));
                    }
                }
            }
        } catch (Exception ignored) {
        }
    }

    private static List<String> performTargets(PerformStatement perform) {
        List<String> out = new ArrayList<>();
        PerformProcedureStatement proc = perform.getPerformProcedureStatement();
        if (proc == null) return out;  // inline PERFORM has no procedure target
        for (Call call : proc.getCalls()) {
            if (call.getName() != null) out.add(call.getName().toUpperCase());
        }
        return out;
    }
}
