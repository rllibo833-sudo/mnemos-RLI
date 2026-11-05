package org.beyondlight;

import java.util.*;

/** Conservative labels for distinct evidence layers. Experimental support requires direct data linkage. */
public final class FeasibilityClassification {
    public record Report(List<String> classifications, List<String> reasons, List<String> missingEvidence,
                         String conclusion, boolean experimentallySupported) {}
    private FeasibilityClassification() {}

    public static Report evaluate(FeasibilityEngine.Assessment a, boolean numericalBenchmarksPassed,
                                  boolean matchedRawExperimentalData) {
        LinkedHashSet<String> labels=new LinkedHashSet<>(); List<String> reasons=new ArrayList<>(), missing=new ArrayList<>();
        if (a==null) return new Report(List.of("INSUFFICIENT_DATA"),List.of("No feasibility assessment was supplied."),List.of("assessment"),"No conclusion",false);
        boolean math=a.mathematical().status().equals(FeasibilityEngine.MAT_VALID);
        boolean phys=a.conservation().status().equals(FeasibilityEngine.PHYS_OK)&&a.energyThermal().status().equals(FeasibilityEngine.PHYS_OK);
        boolean physicalBad=a.conservation().status().equals(FeasibilityEngine.PHYS_BAD)||a.energyThermal().status().equals(FeasibilityEngine.PHYS_BAD);
        boolean engBad=a.engineering().status().equals(FeasibilityEngine.ENG_BAD)||a.engineering().status().contains("INFEASIBLE");
        boolean theoretical=a.overallClassification().equals(FeasibilityEngine.THEORY)||a.mathematical().status().equals(FeasibilityEngine.THEORY);
        if(theoretical){labels.add("THEORETICAL_ONLY");reasons.add("Model keluarga ini tidak menyediakan mekanisme gaya dorong dan sumber energi terverifikasi.");}
        if(math){labels.add("MATHEMATICALLY_CONSISTENT");reasons.add("Domain perhitungan dan relasi model berhasil dievaluasi secara matematis.");}
        else if(a.mathematical().status().equals(FeasibilityEngine.MAT_BAD)){labels.add("PHYSICALLY_INCONSISTENT");reasons.add("Input atau persamaan gagal pemeriksaan matematis.");}
        if(physicalBad){labels.add("PHYSICALLY_INCONSISTENT");reasons.add("Sedikitnya satu pemeriksaan konservasi/energi menunjukkan pelanggaran dalam model.");}
        else if(phys){labels.add("PHYSICALLY_CONSISTENT");reasons.add("Pemeriksaan hukum fisika yang diimplementasikan lolos dalam batas model dan toleransinya.");}
        if(!numericalBenchmarksPassed){labels.add("NUMERICALLY_INCONCLUSIVE");missing.add("Benchmark numerik untuk kombinasi model ini belum dinyatakan lulus.");}
        if(matchedRawExperimentalData){labels.add("EXPERIMENTALLY_SUPPORTED");reasons.add("Terdapat data pengukuran mentah yang ditautkan langsung ke model dan kondisi pembanding.");}
        else missing.add("Data eksperimen mentah yang cocok dan ditautkan ke model belum tersedia; ringkasan publikasi tidak dihitung sebagai validasi eksperimen.");
        boolean anyDerived=!a.results().isEmpty();
        if(anyDerived&&!theoretical){labels.add("ENGINEERING_ESTIMATE");reasons.add("Keluaran rekayasa berasal dari model dan parameter yang diberikan; bukan sertifikasi rancangan.");}
        if(a.engineering().status().equals(FeasibilityEngine.ENG_BAD)){labels.add("ENGINEERING_INFEASIBLE");reasons.add("Pemeriksaan rekayasa menemukan batas yang gagal berdasarkan data yang tersedia.");}
        else if(a.engineering().status().equals(FeasibilityEngine.MISSING)||a.engineering().status().contains("MISSING")||a.engineering().status().contains("INCOMPLETE")){labels.add("INSUFFICIENT_DATA");missing.add("Properti material, kapasitas sistem, atau spesifikasi komponen belum lengkap.");}
        else if(a.engineering().status().equals(FeasibilityEngine.ENG_OK)&&!a.engineering().checks().isEmpty()){labels.add("ENGINEERING_SCREENING");reasons.add("Penyaringan massa/daya komponen lolos pada properti yang diketahui; belum menilai manufaktur atau kualifikasi.");}
        if(labels.isEmpty())labels.add("INSUFFICIENT_DATA");
        if(math&&!numericalBenchmarksPassed)labels.add("NUMERICALLY_INCONCLUSIVE");
        return new Report(List.copyOf(labels),List.copyOf(reasons),List.copyOf(missing),"Tidak ada label ini yang membuktikan mesin nyata dapat dibuat.",matchedRawExperimentalData);
    }
}
