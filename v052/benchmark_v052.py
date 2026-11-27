"""Hand-labelled synthetic fixtures; not claims about real publications.
Each row: query, clearly relevant title, related-but-less-direct title, off-topic title.
Cases span social science, politics, archives, history, philosophy, esotericism,
education, medicine, economics, physical sciences and technology.
"""
CASES=(
 ('Hatred in Society','Collective hatred and societal conflict','The psychology of dehumanization','Fairy Tales in Modern Society'),
 ('Political propaganda','Political propaganda in election campaigns','Media framing and political parties','Propagation of acoustic waves'),
 ('Economic poverty','Economic poverty and household income','Income inequality and economic deprivation','Poverty of the imagination in poetry'),
 ('Government surveillance','Government surveillance and privacy','Electronic surveillance and privacy monitoring','Survival analysis in cancer patients'),
 ('CIA banking','CIA banking and financial networks','Central Intelligence Agency banking records','Central Intelligence Agency historical records'),
 ('FBI','Federal Bureau of Investigation records','FBI files from field offices','Federal Reserve banking reports'),
 ('FOIA','Freedom of Information Act requests','Government transparency and public records disclosure','Freedom of movement in animals'),
 ('Remote viewing','Remote viewing experimental protocols','Anomalous cognition in laboratory studies','Remote video viewing of security cameras'),
 ('Central banking','Central banking and monetary institutions','Monetary policy and interest rate decisions','River bank erosion and sediments'),
 ('Cognitive dissonance','Cognitive dissonance in decision making','Belief inconsistency and motivated reasoning','Cognitive development in childhood'),
 ('Groupthink','Groupthink in institutional decisions','Consensus seeking and group decision making','Group theory in abstract algebra'),
 ('Freemasonry','Freemasonry and lodge history','Masonic ritual and fraternal orders','Construction of masonry bridges'),
 ('Hermeticism','Hermeticism and its intellectual tradition','Corpus Hermeticum textual studies','Hermetic sealing of electronic components'),
 ('Gnosticism','Gnosticism and early religious texts','Nag Hammadi manuscripts and gnostic texts','Diagnostic imaging methods'),
 ('Ancient Egypt','Ancient Egypt and pharaonic administration','Egyptology and Egyptian archaeology','Modern Egypt tourism industry'),
 ('Cold War','Cold War diplomacy and international conflict','Containment policy and nuclear deterrence','Cold water immersion therapy'),
 ('Quantum entanglement','Quantum entanglement in optical systems','Bell inequalities and quantum nonlocality','Entangled fishing nets and marine debris'),
 ('Information theory','Information theory and channel capacity','Mutual information and coding theory','Information about tourist destinations'),
 ('Reading comprehension','Reading comprehension in primary schools','Comprehension monitoring and reading strategies','Reading electric meter measurements'),
 ('Malaria vaccine','Malaria vaccine clinical trials','Malaria immunization and antibody response','Influenza vaccine efficacy'),
 ('Antibiotic resistance','Antibiotic resistance in bacterial populations','Antimicrobial resistance and resistance mechanisms','Electrical resistance in conductors'),
 ('Apollo 11','Apollo 11 lunar landing mission','Eagle lunar module engineering','Apollo theater performance history'),
 ('Economic inequality','Economic inequality and wealth distribution','Income inequality and social mobility','Mathematical inequalities in analysis'),
 ('Climate change','Climate change and atmospheric temperature','Greenhouse gas emissions and climate impacts','Changing organizational leadership climate'),
 ('Whistleblowing','Whistleblowing and public accountability','Protected disclosure and organizational wrongdoing','Acoustic properties of whistles'),
 ('Social identity','Social identity and intergroup relations','Group identification and ingroup bias','Digital identity authentication'),
 ('Financial crisis','Financial crisis and banking failures','Financial instability and systemic financial risk','Family crisis counseling'),
 ('Nuclear deterrence','Nuclear deterrence during geopolitical conflict','Strategic stability and mutual assured destruction','Nuclear magnetic resonance imaging'),
)
LIVE_TOPICS={
 'Zenodo':('Hatred in Society','Remote viewing','Hermeticism','Central banking','Cognitive dissonance'),
 'government-attic':('FBI','FOIA','CIA banking','Government surveillance'),
 'ERIC':('Reading comprehension','Educational inequality','Social identity','Groupthink'),
 'NASA NTRS':('Apollo 11','Spaceflight','Climate change','Dark matter'),
 'arXiv':('Quantum entanglement','Information theory','Machine learning','Dark matter'),
}
