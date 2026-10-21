# Real-data sources for HimanshuDigitalTwin

## 1. ShanghaiT2DM — primary external T2D cohort
- Original collection: https://figshare.com/collections/Diabetes_Datasets_ShanghaiT1DM_and_ShanghaiT2DM/6310860
- Article: https://doi.org/10.1038/s41597-023-01940-7
- Public download used by Glucose-ML: https://ndownloader.figshare.com/files/42966622
- License: CC BY 4.0 (Figshare collection)
- Cohort: 100 people with Type 2 diabetes.
- CGM: 3–14 days per recording period, approximately every 15 minutes.
- Additional data in original release: clinical characteristics, laboratory measurements, medication, insulin/non-insulin therapy, capillary blood glucose, diet records.
- The included `shanghai_t2dm_metadata.csv` is a harmonized metadata table from the open Glucose-ML project and preserves patient IDs 2000–2099.

## 2. CGMacros — primary multimodal personalization cohort
- PhysioNet: https://physionet.org/content/cgmacros/1.0.0/
- DOI: https://doi.org/10.13026/3z8q-x658
- Cohort: 45 people: 15 no diabetes, 16 prediabetes, 14 T2D.
- Roughly 10 days/person.
- Modalities: two CGMs, food macronutrients/photos, physical activity, demographics, anthropometrics, blood biomarkers and microbiome.
- Best use: patient-specific multimodal twin and personalization evaluation.

## 3. BIG IDEAs glycemic wearable dataset — wearable robustness cohort
- PhysioNet: https://physionet.org/content/big-ideas-glycemic-wearable/1.1.3/
- DOI: https://doi.org/10.13026/aw6y-fc44
- License: Open Data Commons Attribution License v1.0.
- Cohort: 16 participants monitored 8–10 days.
- Modalities: Dexcom G6, Empatica E4 HR/BVP/EDA/temperature/accelerometry, food logs, gender and HbA1c.
- Best use: validating sensor ingestion and wearable/CGM temporal alignment, not primary T2D training.

## 4. ICMR-INDIAB — India relevance/evidence only
- ICMR: https://www.icmr.gov.in/advancing-biomedical-research
- Use only for epidemiological/context evidence. Do not use as a CGM training cohort unless patient-level data are separately obtained under appropriate access terms.

## 5. Glucose-ML — harmonization/reference pipeline
- Repository: https://github.com/Augmented-Health-Lab/Glucose-ML-Project
- Provides open download and harmonization scripts for Shanghai, CGMacros, BIG IDEAs and other CGM datasets.
