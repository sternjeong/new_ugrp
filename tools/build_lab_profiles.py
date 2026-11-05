"""Build data/lab_profiles.jsonl from hand-written drafts; every quote must be a verbatim
substring (whitespace-normalized) of one of the lab's collected sections."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from curri.catalog import Catalog

ROOT = Path(__file__).resolve().parents[1]
cat = Catalog(ROOT / 'data')
concepts = {c['id']: c for c in json.load(open(ROOT / 'data/concepts.json'))['concepts']}

def norm(s):
    return re.sub(r'\s+', ' ', s).strip().lower()

# T(concept, role, quote, label_ko=None)
def T(concept, role, quote, label=None):
    assert concept in concepts, concept
    assert role in ('domain', 'method'), role
    return {'concept': concept, 'role': role, 'quote': quote, 'label_ko': label}

def R(concept, role, quote, label=None):
    t = T(concept, role, quote, label); t['source'] = 'reviewer'; return t

# Generic methods that must not connect a lab on their own (reviewer rule, 2026-09-16):
# AI/ML counts as a primary topic only where ML itself is the lab's subject (role=domain).
GENERIC_METHODS = {'machine_learning'}
# Application topics: real, quotable, and useful for interest search, but peripheral to what the lab
# actually trains on. Courses are linked only through core topics (reviewer complaint, 2026-09-16:
# an ML lab's "drug discovery" line pulled in 20+ biology courses).
APPLICATION = {
    'lab_ff0eeeea90a1': {'industrial_ai', 'ubiquitous_mobile_computing'},
    'lab_a803732520d8': {'machine_learning', 'computer_architecture'},
    'lab_0550a1bc6943': {'digital_health_wearables', 'ultrasound_acoustics', 'vr_ar_xr'},
    'lab_d8c476f94f20': {'nanomaterials_2d'},
    'lab_975679fa678a': {'digital_health_wearables', 'power_electronics'},
    'lab_e0f1bf42627c': {'soft_electronics'},
    'lab_96b6fdf81d5f': {'embedded_systems'},
    'lab_5363b8639b6a': {'battery_energy'},
    'lab_51c3f65f66e9': {'embedded_systems'},
    'lab_30b0bf664aa0': {'operating_systems_storage', 'system_security', 'cryptography_privacy'},
    'lab_76892e8a1858': {'operating_systems_storage'},
    'lab_34e9ceeb574e': {'radar_sensing', 'quantum', 'plasma_multiphysics'},
    'lab_ed8b612492ff': {'machine_learning'},
    'lab_db94dcbe5311': {'semiconductor_devices', 'circuit_design'},
    'lab_e6a0e5e047a7': {'education_technology', 'digital_health_wearables', 'nlp'},
    'lab_ab7b31a40d9c': {'robotics', 'haptics', 'materials_science'},
    'lab_093a9ff4a3a5': {'circuit_design'},
    'lab_b2bc3bf02e20': {'radar_sensing'},
    'lab_e5f20d526887': {'generative_models'},
    'lab_aeaeb1d9e45c': {'photonics_optics'},
    'lab_ee13f2464526': {'vr_ar_xr'},
    'lab_29eb07f2a745': {'nlp'},
    'lab_44f00d8a40c9': {'machine_learning', 'biosensors', 'rf_microwave'},
    'lab_a53be44484aa': {'optimization'},
    'lab_4057a0293a7d': {'quantum', 'networking_iot'},
    'lab_bfc5e0710500': {'radar_sensing'},
    'lab_76fadd9041d5': {'computer_graphics', 'data_mining_databases'},
    'lab_cc7673481df3': {'statistics_probability'},
    'lab_c3cd46ef8123': {'world_models_embodied'},
    'lab_7169c8a7f3bf': {'brain_neuroscience'},
    'lab_d666360c983d': {'bioinformatics_molecules', 'digital_health_wearables'},
    'lab_606ba3c69266': {'nlp', 'computer_vision', 'speech_processing', 'efficient_ai'},
    'lab_bc5fde76dc89': {'efficient_ai'},
    'lab_a9231195c8fa': {'social_computing', 'efficient_ai'},
    'lab_65c2c5dbaa3f': {'federated_distributed_learning'},
    'lab_d6a4eaecb65f': {'bioinformatics_molecules'},
    'lab_e42f51e5e604': {'education_technology', 'system_security', 'graph_learning'},
    'lab_fbc718646667': {'speech_processing', 'federated_distributed_learning'},
    'lab_926e0dd80226': {'world_models_embodied', 'nlp'},
    'lab_1604b8a6756c': {'world_models_embodied'},
    'lab_f69dfceb3338': {'hci'},
    'lab_13b74dcc1442': {'networking_iot'},
    'lab_1139ae4ba42f': {'reinforcement_learning', 'system_security', 'embedded_systems'},
    'lab_fbe4dd191302': {'brain_neuroscience', 'robotics'},
    'lab_efef6289aa4f': {'battery_energy'},
    'lab_e448d45da9da': {'networking_iot', 'machine_learning'},
    'lab_2259c59b37c3': {'computer_architecture', 'world_models_embodied'},
}
D = []  # drafts
def lab(lab_id, status, grade, summary, topics, notes=()):
    D.append({'lab_id': lab_id, 'status': status, 'evidence_grade': grade, 'summary_ko': summary, 'topics': topics, 'notes': list(notes)})

lab('lab_ff0eeeea90a1', 'ok', 'unclassified',
    '무선 네트워크·IoT 신호(UWB, 블루투스 등)에 AI를 적용하는 연구와 음성 AI(감정 음성 변환, 음성 대화 시스템)를 함께 다룬다.',
    [T('networking_iot', 'domain', 'aims to develop and expand the use of wireless networks and human voice. We are currently interested in applications of AI in mobile networks and voice processing, and signal processing in wireless networks', 'AI + IoT·무선 네트워크'),
     T('machine_learning', 'method', 'We are currently interested in applications of AI in mobile networks and voice processing'),
     T('speech_processing', 'domain', 'Transform a given utterance into a different emotional style while preserving the linguistic content.', '감정 음성 변환·음성 대화 시스템'),
     T('ubiquitous_mobile_computing', 'domain', 'Leverages a device’s built-in speaker and microphone to interpret its physical surroundings and user interactions.', '음향 센싱·머리 방향 추적'),
     T('industrial_ai', 'domain', 'Process of identifying, isolating, and analyzing malfunctions or failures within a system.', '고장 탐지·진단'),
     T('signal_processing', 'method', 'signal processing in wireless networks')],
    ['홈페이지 본문의 절반 이상이 AI대학원 관련 언론 기사이며 연구 내용과 무관하다.'])

lab('lab_a803732520d8', 'ok', 'research_intro',
    '고속·THz 반도체 소자, 저차원 소재, 양자·열 수송 물리를 다루며, DFT 등 계산 방법과 소자 제작을 병행하는 것으로 보인다.',
    [T('semiconductor_devices', 'domain', 'High Speed/THz Devices', '고속·THz 소자'),
     T('nanomaterials_2d', 'domain', 'Low Dimensional Materials', '저차원 소재'),
     T('semiconductor_devices', 'domain', 'Quantum Transport', '양자 수송'),
     T('thermal_transport', 'domain', 'Thermal Transport', '열 수송'),
     T('computer_architecture', 'domain', 'Next Generation Computing', '차세대 컴퓨팅 소자'),
     T('device_simulation_dft', 'method', 'Density Functional Theory Methods', 'DFT·분자동역학 계산'),
     T('semiconductor_devices', 'domain', 'Interfacial charge and thermal transport in diamond field-effect transistors with c-BN and Al2O3 gate dielectrics', '다이아몬드 FET'),
     T('machine_learning', 'method', 'Ultralow‐Power Real‐Time On‐Chip Thermal Prediction via Finite Element Method–Machine Learning Codesign and Field‐Programmable Gate Array Deployment', 'FEM–기계학습 결합 열 예측')],
    ['연구 소개 페이지는 제목 5개뿐이고 나머지는 구성원 명단이다. DFT·분자동역학은 학생 관심사에서 반복 확인했다.'])

lab('lab_0550a1bc6943', 'ok', 'research_intro',
    '미래 디스플레이 설계, 액정 기반 광학·안테나 소자, 전력변환 회로, VR 멀미 등 디스플레이·배열 기술 전반을 다룬다.',
    [T('display_technology', 'domain', 'Main research topics in WADE are Future Display Design, Future Array Technology, Display and Array Modeling.'),
     T('display_technology', 'domain', 'Smart window technology based on liquid crystals', '액정 스마트 윈도우·필터'),
     T('vr_ar_xr', 'domain', 'Cyber-sickness in virtual reality', 'VR 멀미·HMD 콘텐츠'),
     T('power_electronics', 'domain', 'High gain DC/DC Converter', '고승압 DC/DC 컨버터'),
     T('rf_microwave', 'domain', 'Liquid crystal antennas', '액정 안테나'),
     T('ultrasound_acoustics', 'domain', 'Directional speakers', '지향성 스피커·초음파 응용'),
     T('digital_health_wearables', 'domain', 'QD IR Healthcare application', 'QD 적외선 헬스케어')])

lab('lab_d8c476f94f20', 'ok', 'publications',
    '실리콘 나노구조 기반 열전 소자와 열(포논) 수송, 고전압 FinFET 등 반도체 소자를 연구한다. 연구 소개 페이지 본문은 비어 있어 논문·공지로 추정했다.',
    [T('battery_energy', 'domain', '“서버실·배터리 폐열, 전기가 된다”…포스텍, 실리콘 열전소자 효율 한계 돌파', '실리콘 열전 소자'),
     T('thermal_transport', 'domain', 'Thermal conductivity reduction in silicon nanotubes through phonon localization', '나노구조 포논 수송'),
     T('semiconductor_devices', 'domain', 'High-voltage FinFET with floating poly and high-k material for enhanced intrinsic gain and safe operating area', '고전압 FinFET'),
     T('device_simulation_dft', 'method', 'Monte Carlo study of phonon transport in surface modulated silicon nanowires', '몬테카를로 포논 시뮬레이션'),
     T('nanomaterials_2d', 'domain', 'silicon nanotubes', '실리콘 나노튜브·나노선')],
    ['2027년도 대학원생 모집 공지에 “열전 에너지 기술” 분야가 명시되어 있다(모집 현황은 미검증).'])

lab('lab_975679fa678a', 'ok', 'research_intro',
    '제철·전력·배터리 등 산업 현장의 데이터를 딥러닝과 제어로 다루는 지능제어 연구실이다. 결함 검출, 이상 탐지, 배터리 상태 추정, 전동기 고장 진단이 반복 등장한다.',
    [T('industrial_ai', 'domain', 'GRINDING 자동화를 위한 스카핑 슬라브의 피팅 결함 검출 딥러닝 모델에 대한 연구 개발, 포스코', '제철 공정 결함 검출'),
     T('industrial_ai', 'domain', 'Noise-robust anomaly detection framework using temporal features for industrial applications', '산업 이상 탐지'),
     T('machine_learning', 'method', '딥러닝 활용한 영구자석 동기전동기의 선간 단락 고장 조기진단에 관한 기초 연구'),
     T('battery_energy', 'domain', '전류 및 온도를 고려한 리튬 이온 배터리의 등가모델 기반 상태 진단 알고리즘 개발', '리튬이온 배터리 상태 추정'),
     T('control_theory', 'method', '형상 제어를 위한 ZRM 시뮬레이터 개발 및 제어 알고리즘 개선, 포스코'),
     T('computer_vision', 'method', 'MULTI-SPECTRAL 드론영상에 대하여 FCN 기반 딥러닝 및 영상처리를 이용한 송전선로 및 폴리머 현수애자 검출 알고리즘 개발'),
     T('power_electronics', 'domain', 'Optimal design of fault-tolerant outer-rotor spoke-type PMSM with single-layer FSCW and magnetic notches using Kriging and NSGA-2 for satellite CMGs', '전동기 설계·고장 진단'),
     T('digital_health_wearables', 'domain', 'Physiological signal based drowsiness detecting system using feedback data', '생체신호 기반 졸음 감지')],
    ['연구 실적 목록은 2015~2019년 과제이며, 2025~2026년 논문으로 현재 방향을 보강했다.'])

lab('lab_5675123dff8f', 'insufficient', 'none',
    '수집된 페이지가 연구·행정 인력 명단뿐이라 연구 주제를 확인할 수 없다.',
    [], ['재수집 필요: 연구 소개 페이지 부재. 2026-09-16 검토자 확인: 홈페이지에 한글 연구 설명이 있으나 수집되지 않음.'])

lab('lab_e0f1bf42627c', 'ok', 'research_intro',
    '산화물 반도체(IGZO) 소자·차세대 메모리와, 웨어러블 기기용 AI 음성 향상(골전도 마이크 결합, 경량화)을 함께 연구한다.',
    [T('speech_processing', 'domain', 'we develop a multimodal speech enhancement model that produces clear and natural speech', '멀티모달 음성 향상'),
     T('efficient_ai', 'method', 'The model is further compressed through pruning and quantization, enabling efficient real-time deployment on mobile and wearable devices.'),
     T('soft_electronics', 'domain', 'AI Speech Enhancement Model for Smart Wearable Devices', '스마트 웨어러블 기기'),
     T('semiconductor_devices', 'domain', 'Quantitative Analysis and Mitigation Strategy for Hot Carrier Degradation in a-IGZO Transistor', '산화물 반도체 트랜지스터'),
     T('semiconductor_devices', 'domain', 'Recent Progress and Opportunities in Oxide Semiconductor Devices for In-Memory and Neuromorphic Computing', '차세대 메모리·뉴로모픽 소자'),
     T('machine_learning', 'method', 'Throat and acoustic paired speech dataset for deep learning-based speech enhancement')],
    ['모집 안내: 전자전기 외 재료·화공·기계·물리 전공도 환영한다고 명시. 매년 2~4명 모집(현재 상태 미검증).'])

lab('lab_96b6fdf81d5f', 'ok', 'reviewer_verified',
    '수학적 제어 이론을 개발하고 로봇, 항공우주 비행체, 사이버물리 시스템 등 실제 제어 시스템에 응용한다. 수집 본문에는 연구원 관심사만 있었고, 검토자가 홈페이지에서 직접 확인한 문장을 근거로 보강했다.',
    [R('control_theory', 'domain', 'The focus of the laboratory is to develop mathematical control theories and their applications to practical control systems such as robotics, aerospace vehicles, cyber-physical systems, and so on.', '수학적 제어 이론'),
     R('robotics', 'domain', 'The focus of the laboratory is to develop mathematical control theories and their applications to practical control systems such as robotics, aerospace vehicles, cyber-physical systems, and so on.', '로봇·항공우주 제어 응용'),
     R('embedded_systems', 'domain', 'The focus of the laboratory is to develop mathematical control theories and their applications to practical control systems such as robotics, aerospace vehicles, cyber-physical systems, and so on.', '사이버물리 시스템'),
     T('control_theory', 'method', 'Consensus control of multi-agent systems', '다중 에이전트 합의 제어')],
    ['재수집 필요: 연구 소개·논문 목록 본문 부재. 2026-09-16 검토자가 홈페이지 소개 문장을 직접 확인해 추가.'])

lab('lab_15fd7dce2706', 'ok', 'research_intro',
    '제어·추정·신호처리에 적용되는 볼록 최적화 이론을 중심으로 연구하며 기업 과제도 수행한다.',
    [T('control_theory', 'domain', 'We are currently focusing on convex optimization theories applied to control, estimation, and signal processing'),
     T('optimization', 'method', 'convex optimization theories applied to control, estimation, and signal processing', '볼록 최적화'),
     T('signal_processing', 'method', 'We are actively seeking passionate individuals interested in control theory and adaptive filter.', '적응 필터'),
     T('control_theory', 'domain', 'An LMI Approach to Admissibility Analysis and H∞ Observer-Based Control Design with Fault Estimation for Singular Fractional-Order Systems', 'LMI·강인 제어')])

lab('lab_5363b8639b6a', 'ok', 'research_intro',
    '드론, 강화학습 기반 제어, 센서 융합, 리튬이온 배터리 모델링의 세 그룹으로 구성된 컴퓨팅·제어 연구실이다.',
    [T('slam_navigation', 'domain', 'Drone group has focused on the development of autonomous aerial vehicles.', '자율 비행 드론'),
     T('slam_navigation', 'domain', '3D omnidirectional depth sensors and autonomous navigation solutions have been developed', '3D 깊이 센서·자율 항법'),
     T('reinforcement_learning', 'method', 'our research puts much weight on recent state-of-the-art reinforcement learning instead of classical control approaches'),
     T('control_theory', 'domain', 'Control group has worked on developing a variety of control systems for autonomous vehicles and industrial facilities in POSCO.'),
     T('radar_sensing', 'method', 'sensor fusion technologies with Lidars, Radars, and cameras have been the important research issues', '라이다·레이더·카메라 융합'),
     T('battery_energy', 'domain', 'Energy group is focussing on constructing a sophisticated model of Li-ion batteries to monitor their internal states consistently.'),
     T('machine_learning', 'method', 'To identify model parameters, machine learning based researches have been conducted on a data-driven basis.'),
     T('robotics', 'domain', 'coordinating a swarm of drones for mission accomplishment', '군집 드론')])

lab('lab_51c3f65f66e9', 'thin', 'research_intro',
    '전력 컨버터의 고급 제어, 분산 에너지 네트워크용 컨버터, FPGA 기반 고장 허용 제어를 다룬다. 제목 수준의 정보만 수집됐다.',
    [T('power_electronics', 'domain', 'Advanced Control Technologies for Power Converters'),
     T('control_theory', 'method', 'Advanced Control using FPGA - Fault Tolerant control, Parameter Estimation'),
     T('battery_energy', 'domain', 'Advanced Control Technologies for Converters in Distributed Energy Networks', '분산 에너지 네트워크'),
     T('embedded_systems', 'method', 'Advanced Control using FPGA', 'FPGA 구현')])

lab('lab_30b0bf664aa0', 'ok', 'research_intro',
    '정보이론·부호이론·최적화·학습이론을 도구로, 효율적·강건·안전한 정보 처리와 통신(시맨틱 통신, 신경망 디코더, 메모리 부호화, 동형암호)을 연구한다.',
    [T('information_theory_coding', 'method', 'leveraging and extending mathematical tools from information theory, coding theory, optimization, and learning theory.'),
     T('wireless_communications', 'domain', 'Semantic-aware and task-oriented communications (integrated communication and computation)', '시맨틱·과제 지향 통신'),
     T('machine_learning', 'method', 'Neural decoders for channel coding', '신경망 채널 디코더'),
     T('operating_systems_storage', 'domain', 'Coding and quantization for memories and processing-in-memory', '메모리·SSD 부호화'),
     T('cryptography_privacy', 'method', 'Efficient algorithms under homomorphic encryption constraints', '동형암호 기반 AI 추론'),
     T('federated_distributed_learning', 'method', 'Distributed inference and learning under resource constraints'),
     T('system_security', 'domain', 'Information-theoretic security and privacy', '정보이론적 보안')],
    ['학부 인턴이 JSAC·ISIT 등 논문 저자로 참여한 사례를 명시. 인턴 지원 시 CV·성적표 면담 권장.'])

lab('lab_76892e8a1858', 'ok', 'unclassified',
    '이동·위성 통신과 데이터 저장 시스템을 위한 오류제어 부호와 수열 설계를 연구한다. 본문이 3G·4G 시대 기준이라 최신성은 미확인이다.',
    [T('information_theory_coding', 'method', 'develop error-control technologies and sequences for reliable and robust communication systems', '오류제어 부호·수열'),
     T('wireless_communications', 'domain', 'LDPC/RA/CT/Turbo 부호 및 시공간(Space-Time) 부호 등의 MIMO 기술들에 대한 효율적인 부호화/복호화 알고리즘을 활발하게 연구하고 있다'),
     T('operating_systems_storage', 'domain', '이동 통신 시스템, 위성 통신 시스템 그리고 데이터 저장 시스템과 같은 디지털 통신 시스템을 위한 오류제어기술과 수열을 개발해 왔다', '데이터 저장 시스템 부호')],
    ['홈페이지 본문이 오래된 표준(IMT-2000, 802.16e) 기준. 현재 연구 방향 재확인 필요.'])

lab('lab_34e9ceeb574e', 'ok', 'research_intro',
    '전산 전자기학(FEM·FDTD 등 완전파 모델링, 기계학습 결합, 대규모 병렬화)과 플라즈마·양자 전자기·대기 전파 등 다중물리 모델링을 다룬다.',
    [T('electromagnetics', 'domain', 'Full-wave modeling techniques (FEM, FDTD, MOM, DEC, DGTD)', '완전파 전자기 모델링'),
     T('machine_learning', 'method', 'Machine-learning-based CEM approach', '기계학습 기반 전산전자기'),
     T('high_performance_computing', 'method', 'Large-scale problem acceleration (DDM, CPU & GPU parallelization)'),
     T('plasma_multiphysics', 'domain', 'High energy plasma system modeling &'),
     T('quantum', 'domain', 'Computational Macroscopic Quantum Electromagnetics', '거시 양자 전자기'),
     T('radar_sensing', 'domain', 'Chaff Cloud RCS Modeling', '레이더 단면적 모델링'),
     T('device_simulation_dft', 'method', 'Particle-in-Cell algorithm', 'PIC 시뮬레이션')])

lab('lab_ed8b612492ff', 'ok', 'unclassified',
    '마이크로파·밀리미터파·테라헤르츠 회로(RFIC 그룹, 송호진)와 안테나·전자기(안테나 그룹, 홍원빈)를 공동 운영하는 MADs 연구실이다. 6G 통신, 레이더, 위성통신 응용이 논문에 나타난다.',
    [T('rf_microwave', 'domain', 'specializes in researching a variety of topics within applied EM and RF Circuits including Microwave, Millimeter-wave and Terahertz Circuits, Antennas, Wave Propa gation Studies for Wireless Applications, Radars and EM Metamaterials.'),
     T('circuit_design', 'method', 'Stacked-FET CMOS Power Amplifier in Millimeter-Wave and Sub-THz Band: Design and Considerations', 'CMOS 전력증폭기·RFIC'),
     T('wireless_communications', 'domain', 'Wideband Single Conductive Layer Glass Picture Frame Electromagnetic Skin for 6G Upper-Mid Band Indoor Communication', '6G 통신용 안테나'),
     T('radar_sensing', 'domain', 'An E-Band Radar Transceiver With Daisy-Chained Wireless Chirp Synchronization for Scalable Multistatic Radar Networks', 'E-band 레이더 송수신기'),
     T('machine_learning', 'method', 'AI-Assisted Antenna State Selection for Throughput Optimization in Higher-Order MIMO Mobile Terminals Under Arbitrary User Scenarios', 'AI 보조 안테나 선택')],
    ['교수 두 명이 홈페이지를 공유한다. 그룹 구분(RFIC/Antenna)은 원문에서 확인.'])

lab('lab_db94dcbe5311', 'ok', 'research_intro',
    '이온 트랩 기반 양자컴퓨팅·양자 시뮬레이션, 나노공정으로 만드는 양자 소자(이온트랩 칩, 초전도 큐비트), 원자-공진기 양자 네트워크를 실험적으로 연구한다.',
    [T('quantum', 'domain', 'We carry out quantum computing and quantum simulation experiments with a string of ions confined in a linear Paul trap.'),
     T('semiconductor_process_packaging', 'method', 'We develop scalable quantum devices using state-of-the-art nanofabrication technologies.', '양자 소자 나노공정'),
     T('photonics_optics', 'domain', 'The goal of this project is to develop an atom-cavity quantum network node.', '원자-공진기 양자 인터페이스'),
     T('circuit_design', 'method', 'A Cryo-CMOS 64-Channel Bias Generator IC for Surface Ion Trap', '극저온 CMOS 제어 회로'),
     T('semiconductor_devices', 'domain', 'Neuromorphic  semiconductor devices', '뉴로모픽 반도체 소자')])

lab('lab_e6a0e5e047a7', 'ok', 'research_intro',
    '인간-AI 공생, 유비쿼터스 센싱, 모바일 XR·텔레프레즌스, 실세계 소셜 컴퓨팅, 온디바이스 AI를 아우르는 HCI·모바일 컴퓨팅 연구실이다.',
    [T('hci', 'domain', 'Human-AI Interaction & Symbiosis', '인간-AI 상호작용'),
     T('ubiquitous_mobile_computing', 'domain', 'Pervasive Sensory Augmentation for Interactive Everyday Spaces', '유비쿼터스 센싱'),
     T('vr_ar_xr', 'domain', 'Mobile Extended Reality (XR) & Telepresence: Future of Human Presence'),
     T('social_computing', 'domain', 'IoT-powered Real-world Social Computing'),
     T('efficient_ai', 'method', 'On-device AI: Acceleration for Pervasive AI'),
     T('nlp', 'method', 'Pervasive sensing & Large Language Model (LLM) for personalized vocabulary assessment-intervention for children', 'LLM 기반 개인화 에이전트'),
     T('digital_health_wearables', 'domain', 'CapWear: Smart Footwear for Peripheral Perfusion Monitoring by Continuous Plantar Capillary Refill Time Estimation', '웨어러블 건강 모니터링'),
     T('education_technology', 'domain', 'personalized vocabulary assessment-intervention for children', '아동 어휘 평가·개입')])

lab('lab_e98e92b0be8c', 'thin', 'unclassified',
    '반도체 소자와 공정을 다루는 나노소자·공정 연구실로, 실리콘 기반 바이오센서, 나노 소자 모델링, SiC 접합이 연구 분야로 적혀 있다.',
    [T('semiconductor_devices', 'domain', '반도체 소자 및 공정에 관심있는 대학원생을 모집합니다.'),
     T('biosensors', 'domain', 'Silicon-based Bio Sensors', '실리콘 바이오센서'),
     T('device_simulation_dft', 'method', 'Nano Device Modeling', '나노 소자 모델링'),
     T('semiconductor_process_packaging', 'domain', 'SiC Contact', 'SiC 접합 공정')],
    ['학부 연구참여 학생 모집 문구가 있다(현재 상태 미검증).'])

lab('lab_ab7b31a40d9c', 'ok', 'research_intro',
    '디스플레이(OLED·LCD·AR/MR 마이크로 디스플레이), 액정·유기 레이저, 유연·신축 전자, 햅틱, 소프트 로봇, 센서까지 소프트 소재 기반 전자 소자를 폭넓게 다룬다.',
    [T('display_technology', 'domain', 'We research various technologies for our better livings with electronic technologies in terms of display, emerging device and soft electronics.'),
     T('display_technology', 'domain', 'Micro Display for AR/MR', 'AR/MR용 마이크로 디스플레이'),
     T('photonics_optics', 'domain', 'Chiral LC Laser', '키랄 액정·유기 레이저'),
     T('soft_electronics', 'domain', 'Stretchable Electronics', '신축·웨어러블·섬유 전자'),
     T('haptics', 'domain', 'Display Integrated Haptic', '디스플레이 일체형 햅틱·스피커'),
     T('robotics', 'domain', 'Electro Active Polymer', '전기활성 고분자·소프트 로봇'),
     T('semiconductor_devices', 'domain', 'New FET and Semiconductor', '신규 FET·메모리 소자'),
     T('materials_science', 'domain', 'Monolithic Opto-Acoustic Synesthetic Transduction of Color and Sound in a Single Chiral Liquid Crystal Elastomer', '액정 엘라스토머 소재')])

lab('lab_093a9ff4a3a5', 'ok', 'publications',
    '산화물·텔루륨 등 초박막 채널 트랜지스터의 신뢰성과 신규 소자 구조(안티앰비폴라 스위치, 3진 인버터)를 연구한다. 연구 소개 페이지 본문은 비어 있어 논문 제목으로 추정했다.',
    [T('semiconductor_devices', 'domain', '1/f noise free carrier transport in phase composite ZnO MOSFETs', '산화물 반도체 MOSFET'),
     T('semiconductor_devices', 'domain', 'Unveiling and Mitigating Hidden Border Trap-Like Defects in Ultrathin Tellurium FETs for Reliable Dynamic Operation', '초박막 Te FET 신뢰성'),
     T('nanomaterials_2d', 'domain', 'Ultrathin Tellurium FETs', '초박막 채널 소재'),
     T('circuit_design', 'domain', 'Co-Integration of a ZnO–Te Anti-Ambipolar Switch and CFETs Enabling a Pull-Middle Architecture for Standard Ternary Inverters', '신소자 기반 3진 논리 회로')])

lab('lab_b2bc3bf02e20', 'ok', 'publications',
    '무선통신(MIMO, 채널 추정, 시맨틱 통신)과 기계학습·연합학습을 결합하는 연구실이다. 연구 소개 페이지 대신 구성원 관심사와 논문으로 파악했다.',
    [T('wireless_communications', 'domain', 'UV3CP: Universal ViT-based 3D Channel Predictor for MIMO-OFDM Systems', 'MIMO-OFDM 채널 예측'),
     T('wireless_communications', 'domain', 'Semantic Feature Channel Optimization: A Unified Framework for Analog and Digital Semantic Communications', '시맨틱 통신'),
     T('federated_distributed_learning', 'method', 'Sparse-SignSGD with Majority Vote: Communication-Efficient Distributed Learning Under Data Heterogeneity', '통신 효율적 분산 학습'),
     T('machine_learning', 'method', 'Universal ViT-based 3D Channel Predictor', '통신을 위한 딥러닝'),
     T('radar_sensing', 'domain', 'Integrated Sensing and Communications', '센싱·통신 통합')])

lab('lab_e5f20d526887', 'ok', 'research_intro',
    '3D 복원, 전산 이미징, 시각 합성, 계산 사진학 등 그래픽스·비전·기계학습·광학이 교차하는 비주얼 컴퓨팅을 연구한다.',
    [T('computer_graphics', 'domain', 'The primary goal of our research is to develop theory, algorithm, and system for visual computing.'),
     T('computer_vision', 'method', 'we conduct interdisciplinary research at the intersection of computer graphics, computer vision, machine learning, and optics.'),
     T('computer_graphics', 'domain', 'We develop algorithms and systems to reconstruct our real world\'s 3D geometry and appearance.', '3D 복원'),
     T('computational_imaging', 'domain', 'We jointly develop theories, algorithms, and systems to achieve a superhuman vision in the form of new imaging and display systems.', '전산 이미징·계산 사진학'),
     T('generative_models', 'method', 'We develop algorithms that can synthesize new visual data with machine creativity.', '시각 합성'),
     T('generative_models', 'method', 'Learning Zero-Shot Subject-Driven Video Generation Using 1% Compute', '비디오 생성')],
    ['cg.postech.ac.kr 논문 페이지는 이승용 교수와 공유된다. 연구실 정체성 확인 필요.'])

lab('lab_aeaeb1d9e45c', 'ok', 'publications',
    '초분광·편광·라이다 등 새로운 이미징 시스템과 역렌더링, 메타렌즈 등 전산 이미징을 연구한다. 연구 소개 본문이 비어 있어 논문 제목으로 추정했다.',
    [T('computational_imaging', 'domain', 'Broadband Hyperspectral 3D Imaging using Dispersed Structured Light', '초분광 3D 이미징'),
     T('computational_imaging', 'domain', 'Polarimetric Full-Wavefield Coherent Lidar', '편광 라이다'),
     T('computer_graphics', 'domain', 'Ambient-robust Inverse Rendering using Active RGB-NIR Imaging', '역렌더링'),
     T('photonics_optics', 'domain', 'Actively Tunable Metalens with Varying Field-of-Views', '메타렌즈 광학'),
     T('computer_vision', 'method', 'Depth-guided Multi-view Exposure Bracketing for HDR Robot Vision', 'HDR 로봇 비전')])

lab('lab_c01681ff0aa2', 'ok', 'publications',
    '3D 기하 복원과 기하 최적화 등 컴퓨터그래픽스를 연구한다. 연구 소개가 없고 논문 페이지가 조성현 교수 연구실과 공유되어, 이승용 교수 저자 논문만 근거로 삼았다.',
    [T('computer_graphics', 'domain', 'StructureGS: Structure-aware Gaussian Splatting for Articulated Object Reconstruction', '가우시안 스플래팅 3D 복원'),
     T('computer_graphics', 'domain', 'Statistical Gradient Filtering for Geometry Optimization Under Limited Observations', '기하 최적화'),
     T('computer_vision', 'method', 'Articulated Object Reconstruction', '물체 복원')],
    ['공유 홈페이지: cg.postech.ac.kr. 별도 연구실 여부 검토 필요.'])

lab('lab_0cc50bac8f1e', 'thin', 'lab_name',
    '연구실 이름(지능형 레이더 시스템 및 신호처리 연구실) 외의 본문이 수집되지 않았다.',
    [T('radar_sensing', 'domain', '지능형 레이더 시스템 및 신호처리 연구실', '레이더 시스템'),
     T('signal_processing', 'method', '지능형 레이다 시스템 및 신호처리연구실', '레이더 신호처리')],
    ['재수집 필요: 연구 소개·논문 본문 부재.'])

lab('lab_ee13f2464526', 'ok', 'research_intro',
    '블록체인 확장성을 위한 분산 합의와 하이브리드 P2P 네트워크, 5G 기반 영상 스트리밍·AR 서비스 등 네트워크 시스템을 연구한다.',
    [T('distributed_systems_blockchain', 'domain', '블록체인 확장성 확보를 위한 O(N) 메시지 복잡도 및 시간 제약 조건을 만족하는 분산 합의 기술', '블록체인 합의'),
     T('networking_iot', 'domain', '하이브리드 P2P 최적 경로 네트워크 플랫폼 개발', 'P2P 네트워크'),
     T('networking_iot', 'domain', 'Adaptive Viewport-aware 360° Video Streaming System over OpenAirInterface-based 5G Network', '5G 영상 스트리밍'),
     T('vr_ar_xr', 'domain', 'Collaborative Virtual 3D Object Modeling for Mobile Augmented Reality Streaming Services over 5G Networks', '모바일 AR 스트리밍')],
    ['국책과제 개발 기술의 국제 표준 채택을 언급(2025.12 보도).'])

lab('lab_29eb07f2a745', 'ok', 'publications',
    '빅데이터·데이터 관리·데이터베이스 시스템을 연구하며 그래프 엔진과 시맨틱 질의 처리가 최근 논문에 나타난다. 연구 소개 본문은 비어 있다.',
    [T('data_mining_databases', 'domain', 'For undergrads who are interested in big data, data management, and database systems, note that SIGMOD, VLDB, and ICDE are flagship conferences in these fields.'),
     T('graph_learning', 'domain', 'TurboLynx: Schemaless Graph Engine Strikes Back for General-Purpose Analytics', '그래프 데이터 엔진'),
     T('nlp', 'method', 'CADENZA in Action: Breaking the Monolith with Intent-Dependent Plan Spaces for Semantic Queries', '시맨틱 질의 처리')],
    ['학부생에게 SIGMOD·VLDB·ICDE를 목표로 하는 자기주도적 학생을 찾는다고 명시.'])

lab('lab_44f00d8a40c9', 'ok', 'research_intro',
    '펨토초 레이저 기반 테라헤르츠 시간영역 분광(THz-TDS) 시스템을 직접 구축하고, THz 근접장 현미경, 바이오 센싱, 포토닉 소자 설계에 응용한다.',
    [T('thz_spectroscopy', 'domain', 'In our lab, we have built a homemade THz-TDS system which is one of the best with the highest signal-to-ratio (SNR) in the world.'),
     T('photonics_optics', 'method', 'THz-TDS is based on electromagnetic transients excited by femtosecond', '펨토초 레이저 광학'),
     T('thz_spectroscopy', 'domain', 'Reference-free self-calibrating tip-based scattering-type THz near-field microscopy.', 'THz 근접장 현미경'),
     T('biosensors', 'domain', 'Quantitative Label-free Terahertz Sensing of Transdermal Nicotine Delivered to Human Skin.', 'THz 바이오 센싱'),
     T('machine_learning', 'method', 'Enhanced DBR mirror design via D3QN: A reinforcement learning approach.', '강화학습 기반 광소자 설계'),
     T('rf_microwave', 'domain', 'Ultra-compact terahertz 50: 50 power splitter designed by a perceptron-based algorithm.', 'THz 도파로 소자')])

lab('lab_72cb497a6f67', 'insufficient', 'none',
    '홈페이지에서 메뉴 이름 외의 본문이 수집되지 않아 연구 주제를 확인할 수 없다.',
    [], ['재수집 필요.'])

lab('lab_a53be44484aa', 'ok', 'publications',
    '고속 유선 링크 등 회로 설계와 아날로그 레이아웃 자동화(EDA)를 연구하며, 기계학습을 설계 자동화에 적용한다. 연구 소개 본문은 비어 있다.',
    [T('circuit_design', 'domain', 'A Fast Design Optimization of On-Chip Equalizing Links Using Particle Swarm Optimization', '고속 온칩 링크 설계'),
     T('circuit_design', 'domain', 'An On-chip Low-Cost Averaging Digital Sampling Scope for 80-GS/s Measurement of Wireline Pulse Responses', '온칩 계측 회로'),
     T('machine_learning', 'method', 'A Self-Supervised Learning of a Foundation Model for Analog Layout Design Automation', '아날로그 레이아웃 자동화 AI'),
     T('optimization', 'method', 'Particle Swarm Optimization', '설계 최적화')],
    ['메뉴에 Circuit Design, Electronic Design Automation 두 연구 분야가 명시됨.'])

lab('lab_4057a0293a7d', 'thin', 'research_intro',
    '초저전력 SoC, 양자컴퓨팅용 회로, 고속 링크, IoT 디지털 시스템을 다루는 집적회로 연구실이다. 제목 수준의 정보만 수집됐다.',
    [T('circuit_design', 'domain', 'Ultra-low-power system-on-chip (SoC)', '초저전력 SoC'),
     T('quantum', 'domain', 'Quantum computing', '양자컴퓨팅용 제어 회로'),
     T('circuit_design', 'domain', 'High-speed links', '고속 링크'),
     T('networking_iot', 'domain', 'Digital systems for internet-of-things (IoT)', 'IoT 디지털 시스템')],
    ['이문주 연구실 논문에 공저(Cryo-CMOS 이온트랩 제어 IC)로 등장.'])

lab('lab_bfc5e0710500', 'ok', 'research_intro',
    '수중·극한환경에서 사람을 대체하는 필드 로봇을 AI·센싱과 함께 연구한다. 생체모방 수중 로봇, 소나 기반 3D 복원, 수중 조작이 논문에 나타난다.',
    [T('underwater_field_robotics', 'domain', 'we are dedicated to unveiling the extremene environments by utilizing field robotics, AI, and perception.'),
     T('robotics', 'domain', '극한환경로봇연구실에서는 필드 로보틱스, 인공지능, 센싱 기술 등을 통해 극한환경에서 사람을 대체할 수 있는 로봇 기술에 대해서 연구합니다.'),
     T('underwater_field_robotics', 'domain', 'Development of Bioinspired Multimodal Underwater Robot "HERO-BLUE" for Walking, Swimming, and Crawling', '생체모방 수중 로봇'),
     T('radar_sensing', 'method', 'Multi-Sonar Fusion-based Precision Underwater 3D Reconstruction for Optimal Scan Path Planning of AUV', '소나 융합 3D 복원'),
     T('machine_learning', 'method', 'field robotics, underwater sensing & perception, and AI', '수중 인식 AI')],
    ['2026학년도 2학기 신입 대학원생 모집 공지(2025.06). 현재 상태 미검증.'])

lab('lab_76fadd9041d5', 'ok', 'research_intro',
    '동적 환경에서의 알고리즘·자료구조, 계산기하(형상 매칭·근사, 스카이라인 질의, 주조 문제)를 이론적으로 연구하고 내비게이션·치아 정렬·반도체 설계에 응용한다.',
    [T('algorithms_theory', 'domain', 'we are interested in designing algorithms and data structures that could solve various problems in dynamic environments.'),
     T('algorithms_theory', 'domain', 'we are applying algorithms in computational geometry to solve various geometric problems in the practical world, such as navigation system, teeth alignment, and semiconductor design.', '계산기하 응용'),
     T('data_mining_databases', 'domain', 'We study spatial skyline query processing problem, which enables an intelligent and efficient access to massive spatial data.', '공간 데이터 질의'),
     T('computer_graphics', 'domain', 'Substituting a complex geometric shape by a “simpler” one is motivated by many applications.', '형상 근사·매칭')])

lab('lab_cc7673481df3', 'ok', 'research_intro',
    '평면 그래프·기하 그래프 위의 알고리즘(서로소 경로, FVS, 거리 오라클)과 매개변수 복잡도, 랜덤 기하 그래프를 연구하는 이론 전산 연구실이다.',
    [T('algorithms_theory', 'domain', 'The FVS problem is NP-hard, but in the parametrized complexity theory, we analyze the running time of an algorithm with respect to the input size and a new parameter.', '매개변수 복잡도'),
     T('algorithms_theory', 'domain', 'Distance Oracles for Geometric Graphs', '기하 그래프 자료구조'),
     T('statistics_probability', 'method', 'Geometric random graphs can be models for many real-world graphs.', '랜덤 기하 그래프'),
     T('algorithms_theory', 'domain', 'Disjoint Paths on Planar Graphs', '평면 그래프 알고리즘')],
    ['이론 전산 관례에 따라 저자 알파벳순 표기.'])

lab('lab_c3cd46ef8123', 'ok', 'research_intro',
    '추천시스템, 시계열 파운데이션 모델, 멀티모달 RAG, 로봇 파운데이션 모델(VLA) 등 데이터 인텔리전스 전반을 다루며 학부 인턴 프로젝트를 명시한다.',
    [T('recommender_systems', 'domain', 'Continual and federated recommender system'),
     T('time_series', 'domain', 'Time-series foundation models'),
     T('nlp', 'method', 'Multimodal RAG', '멀티모달 RAG·LLM'),
     T('world_models_embodied', 'domain', 'Time-aware multi-modal VLA Models', 'VLA·로봇 파운데이션 모델'),
     T('machine_learning', 'domain', 'Undergraduates interested in research internships are encouraged to take AI-related courses before applying.'),
     T('recommender_systems', 'domain', 'Filling the Gaps: Selective Knowledge Augmentation for LLM Recommenders', 'LLM 추천'),
     T('time_series', 'domain', 'Dynamic Multi-period Experts for Online Time Series Forecasting')],
    ['학부 인턴 모집과 단계별 지도 언급(현재 상태 미검증). AI 관련 과목 선수강 권장.'])

lab('lab_7169c8a7f3bf', 'ok', 'publications',
    '광음향·초음파 영상과 집속 초음파 신경조절 등 생체 광학·음향 이미징을 연구한다. 연구 소개 본문이 비어 있어 논문 제목으로 추정했다.',
    [T('biomedical_imaging', 'domain', 'Multiscale Photoacoustic Imaging of Stroke in Preclinical Models and Future Directions Toward Clinical Translation', '광음향 영상'),
     T('ultrasound_acoustics', 'domain', 'Pulse Repetition Frequency Tuned Low-Intensity Focused Ultrasound Neuromodulation for Tibial Nerve Targeted Bladder Function Modulation', '집속 초음파 신경조절'),
     T('machine_learning', 'method', 'Self-supervised Spatial Interpolation for 3D Photoacoustic Imaging Using Deep Learning', '딥러닝 영상 복원'),
     T('biomedical_imaging', 'domain', 'Virtual histological staining: toward standardization and clinical translation', '가상 조직염색'),
     T('brain_neuroscience', 'domain', 'Ultrasonic Modulation of Brain Glymphatic Transport: From Observations to Theranostic Applications', '뇌 초음파 조절')])

lab('lab_d666360c983d', 'ok', 'publications',
    '초음파 영상 시스템(패치형 프로브), 집속 초음파 치료, 초음파 기반 세포 평가 등 초음파 공학을 연구한다. 연구 소개 본문이 비어 있어 논문 제목으로 추정했다.',
    [T('ultrasound_acoustics', 'domain', 'Real-time Ultrasound Imaging System utilizing Patch-type Ultrasound Probe for Free-Flap Blood Perfusion Monitoring', '패치형 초음파 영상'),
     T('biomedical_imaging', 'domain', 'Focused Ultrasound-Triggered Burst Release and Enrichment of Engineered Bacteria for Tumor Therapy', '집속 초음파 치료'),
     T('bioinformatics_molecules', 'domain', 'UNIQUE: ultrasound non-destructive in-situ quantitative evaluation of stem cell spheroid deformability during differentiation into specific lineages', '줄기세포 초음파 평가'),
     T('digital_health_wearables', 'domain', 'Free-Flap Blood Perfusion Monitoring', '혈류 모니터링')])

lab('lab_606ba3c69266', 'ok', 'research_intro',
    '생체전자·폐루프 기술로 당뇨(인공췌장), 신경조절, 이식형 기기, 유연 전극, 무성 발화 인터페이스 등 임상 적용 가능한 시스템을 만든다. 강화학습·LLM·비전을 도구로 쓴다.',
    [T('bioelectronics_neural', 'domain', 'We advance bioelectronics and closed-loop technology to develop intelligent, clinically applicable solutions that transform patient care and improve health outcomes'),
     T('digital_health_wearables', 'domain', 'For accurate diabetes management, it is important to know when people eat or exercise', '당뇨 관리·웨어러블 감지'),
     T('reinforcement_learning', 'method', 'our research develops a reinforcement learning based fully closed loop artificial pancreas algorithm', '강화학습 인공췌장'),
     T('nlp', 'method', 'By leveraging large language model (LLM), we offer real-time nutrient analysis, dietary coaching.', 'LLM 식단 코칭'),
     T('computer_vision', 'method', 'integrating computer vision technology enables accurate detection and measurement of food type and quantity', '음식 인식 비전'),
     T('bioelectronics_neural', 'domain', 'We are actively researching and developing medical implantable devices and exploring their various clinical applications.', '이식형 의료기기'),
     T('soft_electronics', 'domain', 'Flexible Multi-Channel Electrode', '유연 다채널 전극'),
     T('control_theory', 'method', 'Keywords: Closed-Loop, Neuromodulation, Signal Processing, Optimal Control, Electrophysiology', '폐루프 최적 제어'),
     T('efficient_ai', 'method', 'Automatic Meal and Exercise Detection with Lightweight On-Device AI', '온디바이스 AI'),
     T('speech_processing', 'domain', 'Silent Speech Interfaces', '무성 발화 인터페이스')],
    ['인턴 모집 공고에 필요 역량(PCB 설계, 최적 제어, C/Python/HDL)을 명시(현재 상태 미검증).'])

lab('lab_bc5fde76dc89', 'ok', 'unclassified',
    '컴퓨터비전과 기계학습의 교차점에서 physical AI(월드모델·VLA)의 강건성·효율, 옴니모달 표현, 비전용 상태공간모델을 연구한다.',
    [T('computer_vision', 'domain', 'My research lies at the intersection of computer vision and machine learning.'),
     T('world_models_embodied', 'domain', 'I am particularly interested in improving robustness and efficiency of physical AI (such as world models and vision-language-action models), integrated and compositional representation of omni-modal data, and state space models for vision.'),
     T('machine_learning', 'domain', 'Vision foundation models often fail in adverse weather or low-light conditions.', '강건한 비전 파운데이션 모델'),
     T('efficient_ai', 'method', 'enables world modeling using only 8 tokens', '압축 월드모델')],
    ['대학원생은 AI대학원 소속으로만 모집하며 인턴 경험자 우선(현재 상태 미검증). POSTECH 학부생은 이메일로 인턴 문의 가능하다고 명시.'])

lab('lab_0c3cb4b83023', 'ok', 'unclassified',
    'MRI·PET·CT 등 의료 영상에 통계·기계학습·그래프 이론 모델을 적용해 신경퇴행성 질환과 뇌 기능을 이해하는 의료정보처리 연구실이다.',
    [T('biomedical_imaging', 'domain', 'We do cutting-edge research on Artificial Intelligence and Medical Imaging.'),
     T('brain_neuroscience', 'domain', 'We identify the effects from neurodegenerative diseases for better understanding of brain functions and its progression.'),
     T('machine_learning', 'method', 'We develop novel (statistical, machine learning, graph theoretical) models that are scalable and applicable to real-world imaging data including, but not limited to, medical images such as MRI, diffusion MRI, functional MRI, PET and CT.'),
     T('graph_learning', 'method', 'graph theoretical', '그래프 이론 모델'),
     T('computer_vision', 'method', 'We are also open for various other traditional Computer Vision and Machine Learning problems.')],
    ['ML/CV 팀(김원화)과 CG/CV 팀(Ilwoo Lyu)로 구성. 후자는 데이터에 없음.'])

lab('lab_a9231195c8fa', 'ok', 'publications',
    '대칭·대응·형상 조립 등 기하 구조를 활용한 컴퓨터비전과 효율적 비전 트랜스포머, 월드모델 토크나이저를 연구한다. 연구 소개 본문이 없어 논문 제목으로 추정했다.',
    [T('computer_vision', 'domain', 'Axis-level Symmetry Detection with Group-equivariant Representation', '대칭·대응 검출'),
     T('computer_vision', 'domain', 'Combinative Matching for Geometric Shape Assembly', '기하 형상 조립'),
     T('world_models_embodied', 'domain', 'Planning in 16 Tokens: A Compact Discrete Tokenizer for Latent World Model', '월드모델'),
     T('efficient_ai', 'method', 'MVFormer: Diversifying Feature Normalization and Token Mixing for Efficient Vision Transformers', '효율적 비전 트랜스포머'),
     T('social_computing', 'domain', 'Part-Aware Bottom-Up Group Reasoning for Fine-Grained Social Interaction Detection', '사회적 상호작용 인식')],
    ['곽수하 연구실과 공저가 많고 같은 도메인(cvlab)을 공유한다.'])

lab('lab_65c2c5dbaa3f', 'ok', 'research_intro',
    '비전 기반 로봇 조작 학습, 표 데이터 이해(테이블 QA), 검색 증강 생성(RAG), 블랙박스 최적화, 분산·능동 학습을 연구한다.',
    [T('robotics', 'domain', 'Training robots to perform manipulation tasks from visual inputs is a challenging task.', '비전 기반 로봇 조작'),
     T('nlp', 'domain', 'we are conducting research on table question answering (QA), aiming to enhance LLM’s understanding of tables through techniques such as fine-tuning or prompt engineering.', '테이블 QA·LLM'),
     T('nlp', 'domain', 'We are investigating question answering (QA) utilizing RAG.', 'RAG 기반 QA'),
     T('optimization', 'method', 'We address the challenge of optimizing functions in the absence of derivative information.', '블랙박스 최적화'),
     T('federated_distributed_learning', 'method', 'privacy-preserving distributed learning'),
     T('machine_learning', 'domain', 'Active learning guided by efficient surrogate learners', '능동 학습')])

lab('lab_d6a4eaecb65f', 'ok', 'unclassified',
    '강화학습, 사회적 영향·프라이버시를 고려한 기계학습(크라우드소싱·연합학습), 그래프 딥러닝(신약 발굴·그래프 생성)을 연구하는 기계학습 연구실이다. 교수 4인(김동우·옥정슬·박상돈·박은혁)이 홈페이지를 공유한다.',
    [T('reinforcement_learning', 'domain', 'Structured reinforcement learning'),
     T('reinforcement_learning', 'domain', 'Adaptive sampling algorithms', '적응적 샘플링·밴딧'),
     T('social_computing', 'domain', 'Machine Learning with Social Computing'),
     T('federated_distributed_learning', 'method', 'Distributed and Federated Learning with Privacy'),
     T('graph_learning', 'method', 'Graph-Structured Deep Learning'),
     T('bioinformatics_molecules', 'domain', 'Drug discovery', '신약 발굴'),
     T('generative_models', 'method', 'Graph generative models'),
     T('machine_learning', 'domain', 'We strive to understand human intelligence through the computational lens.')],
    ['박상돈·박은혁 교수는 별도 기록(lab_1604b8a6756c, lab_2259c59b37c3)이 있다. 학부 연구참여 안내 페이지 존재.'])

lab('lab_ebe1bda9a6e9', 'ok', 'publications',
    '단백질 구조 예측, 결정 구조 예측, 분자 발굴 등 과학 분야에 생성모델·LLM 에이전트를 적용하는 AI 연구를 한다. 연구 소개 본문이 없어 논문 제목으로 추정했다.',
    [T('bioinformatics_molecules', 'domain', 'Atom-level Protein Representation Learning Improves Protein Structure Prediction', '단백질 구조 예측'),
     T('materials_science', 'domain', 'Discovering Crystal Structure Prediction Algorithms with an AI Co-Scientist', '결정 구조 예측·AI 과학자'),
     T('bioinformatics_molecules', 'domain', 'INDIBATOR: Diverse and Fact-Grounded Individuality for Multi-Agent Debate in Molecular Discovery', '분자 발굴 LLM 에이전트'),
     T('materials_science', 'domain', 'MADField: Multi-fidelity Amortized Density Field for Adsorption in Nanoporous Materials', '나노다공성 소재 흡착'),
     T('generative_models', 'method', 'Multimodal Crystal Flow: Any-to-Any Modality Generation for Unified Crys', '결정 생성모델'),
     T('nlp', 'method', 'VibeProteinBench: An Evaluation Benchmark for Language-interfaced Vibe Protein Design', '언어 인터페이스 단백질 설계')])

lab('lab_e42f51e5e604', 'ok', 'research_intro',
    '질의응답, 대화 시스템, 음성을 축으로 하는 자연어처리 연구실이다. 요약, 억양 음성인식, 독해 문항 생성, LLM 백도어 방어 등이 최근 논문에 나타난다.',
    [T('nlp', 'domain', 'Question Answering'),
     T('nlp', 'domain', 'Dialogue System', '대화 시스템'),
     T('speech_processing', 'domain', 'Mixture-of-Experts with Intermediate CTC Supervision for Accented Speech Recognition', '음성 인식'),
     T('nlp', 'domain', 'Segment-level Tree Search for Long Meeting Document Summarization', '문서 요약'),
     T('education_technology', 'domain', 'A Multi-Agent Framework for Feature-Constrained Difficulty Control in Reading Comprehension Item Generation', '독해 문항 생성'),
     T('system_security', 'domain', 'Merging Triggers, Breaking Backdoors: Defensive Poisoning for Instruction-Tuned Language Models', 'LLM 백도어 방어'),
     T('graph_learning', 'method', 'Ontology-Free General-Domain Knowledge Graph-to-Text Generation Dataset Synthesis using Large Language Model', '지식그래프-텍스트 생성')])

lab('lab_a6e4e512ed83', 'thin', 'unclassified',
    '대규모 기계학습을 위한 최적화를 연구하는 계산 최적화 연구실이다. 개인 홈페이지 한 문장만 수집됐다.',
    [T('optimization', 'domain', 'I am interested in optimization for large-scale machine learning.'),
     T('machine_learning', 'domain', 'optimization for large-scale machine learning', '대규모 기계학습')],
    ['재수집 필요: 연구 소개·논문 목록 부재.'])

lab('lab_fbc718646667', 'ok', 'research_intro',
    '임베디드 시스템 설계, 고급 메모리 시스템, 딥러닝을 결합해 미래 지능형 컴퓨팅 시스템을 연구한다. 상시 구동 신경망, 연합학습 체크포인트, 음성 활동 검출 논문이 있다.',
    [T('embedded_systems', 'domain', 'our research interests include embedded system design, advanced memory systems, and deep learning.'),
     T('computer_architecture', 'domain', 'advanced memory systems', '메모리 시스템'),
     T('machine_learning', 'method', 'Fast Design Space Exploration for Always-On Neural Networks', '상시 구동 신경망 설계'),
     T('federated_distributed_learning', 'method', 'An Efficient Checkpoint Strategy for Federated Learning on Heterogeneous Fault-Prone Nodes'),
     T('speech_processing', 'domain', 'Supervised Contrastive Learning for Voice Activity Detection', '음성 활동 검출')])

lab('lab_926e0dd80226', 'ok', 'research_intro',
    '정확도·추론 비용·학습 비용의 트레이드오프를 다루는 효율적 AI 연구실이다. 모델 압축·양자화, 신경망 가중치 코덱, 온디바이스 언어모델, VLA용 이미지 압축이 주제다.',
    [T('efficient_ai', 'domain', 'Make AI accessible to everyone with Efficient ML!'),
     T('machine_learning', 'domain', 'Through theories, we seek to characterize such tradeoffs; through algorithms, we seek to achieve Pareto-optimal points on the tradeoff curve.', '학습 이론·알고리즘 편향'),
     T('efficient_ai', 'domain', 'We develop neural data compression algorithms for neural network weights, with applications in LLMs or neural fields', '가중치 압축 코덱'),
     T('nlp', 'domain', 'By crafting new benchmarks, we reveal that on-device LMs often lack auditory commonsense.', '온디바이스 언어모델'),
     T('world_models_embodied', 'domain', 'Learned Image Compression for Vision-Language-Action Models', 'VLA용 이미지 압축'),
     T('efficient_ai', 'domain', 'Activation Quantization of Vision Encoders Needs Prefixing Registers', '비전 인코더 양자화')],
    ['석박사·인턴 지원 폼이 공개되어 있다(현재 상태 미검증).'])

lab('lab_1604b8a6756c', 'ok', 'research_intro',
    '진실하고 안전한 AI를 이론적 보장과 함께 만드는 AI 정렬 연구실이다. 컨포멀 예측·불확실성 정량화, 에이전트 정렬, physical AI 안전, 레드티밍, 코드 모델 보안이 주제다.',
    [T('ai_safety_alignment', 'domain', 'Build truthful, safe, and secure AI systems with theoretical guarantees.'),
     T('ai_safety_alignment', 'domain', 'Conformal Prediction', '컨포멀 예측·불확실성 정량화'),
     T('reinforcement_learning', 'method', 'Align AI agents to be truthful, safe, and secure.', '에이전트 정렬·강화학습'),
     T('world_models_embodied', 'domain', 'Live with safe robots.', 'physical AI 안전'),
     T('system_security', 'domain', 'Make Agentic AI better by Red Teaming.', '레드티밍'),
     T('nlp', 'domain', 'MJ: Multi-turn LLM Jailbreaking via Decomposed Credit Assignment', 'LLM 탈옥·안전'),
     T('system_security', 'domain', 'The Illusion of Rust Safety: Detecting Modular Unsafe Functions with LLMs', 'LLM 기반 소프트웨어 보안')],
    ['ML Lab 공동 홈페이지에도 교수로 등재됨.'])

lab('lab_f69dfceb3338', 'ok', 'publications',
    '로봇 학습 연구실로, 저가 로봇의 그리기 시연, 인간 동작 리타게팅·예측, 음성 비서 기반 물체 검색 등 인간 동작과 로봇 학습을 연결한다. 연구 소개 본문이 없어 논문 제목으로 추정했다.',
    [T('robotics', 'domain', 'Demonstrating Artistic Drawing on Low-Cost Robot', '저가 로봇 시연 학습'),
     T('robotics', 'domain', 'Redefining Data Pairing for Motion Retargeting Leveraging a Human Body Prior', '인간 동작 리타게팅'),
     T('generative_models', 'method', 'Can We Use Diffusion Probabilistic Models for 3D Motion Prediction?', '확산모델 동작 예측'),
     T('computer_vision', 'method', 'Intention-Conditioned Long-Term Human Egocenteric Action Anticipation', '행동 예측'),
     T('hci', 'domain', 'VAFOR: Proactive Voice Assistant for Object Retrieval in the Physical World', '음성 비서·인간-로봇 상호작용')],
    ['대학원생·연구참여생 모집 배너(현재 상태 미검증). 연구실명 변경(Robot Learning Laboratory).'])

lab('lab_131133154b7e', 'ok', 'unclassified',
    '컴퓨터구조, 운영체제, 시스템 보안, 하드웨어/소프트웨어 협력 설계로 빠르고 안전하며 비용 효율적인 컴퓨팅 시스템을 연구한다(이성진·박지성 공동 지도).',
    [T('computer_architecture', 'domain', 'Our group aims to conduct cutting-edge research and education in a broad range of computer systems, including computer architecture, operating systems, system security, and hardware/software cooperation.'),
     T('operating_systems_storage', 'domain', 'operating systems, system security, and hardware/software cooperation', '운영체제·스토리지'),
     T('system_security', 'domain', 'The overarching goal of our research is to design fast, secure, and cost-effective computing systems that have positive impact on our society and human lives.', '시스템 보안')],
    ['공동 지도 교수 Sungjin Lee는 데이터에 없음. ASPLOS·FAST·SIGMETRICS 논문 게재 소식.'])

lab('lab_13b74dcc1442', 'ok', 'research_intro',
    '블록체인(IoT 결합, 인증, BaaS 감사, BFT 합의), 시스템 보안(TPM 2.0), 스토리지(플래시 RAID, QoS), GPU 가상화를 다루는 시스템 소프트웨어 연구실이다.',
    [T('distributed_systems_blockchain', 'domain', 'Blockchain based User Authentication', '블록체인 인증·합의'),
     T('distributed_systems_blockchain', 'domain', 'Breaking the Straggler Effect: a Relaxed Mempool for High-Throughput and Low-Latency DAG-Based BFT Consensus', 'DAG 기반 BFT 합의'),
     T('networking_iot', 'domain', 'IoT device with blockchain and smart contract based services which provides various, secure and instant services.', 'IoT·스마트 컨트랙트'),
     T('system_security', 'domain', 'Design secure logging scheme based on TPM 2.0 for in-vehicle data protection', 'TPM 기반 보안 로깅'),
     T('operating_systems_storage', 'domain', 'Designing erasure codes and Hybrid-FTL in order to increase the reliability of flash memory without considerably sacrificing the performance of SSDs.', 'SSD 신뢰성·스토리지 QoS'),
     T('operating_systems_storage', 'domain', 'GPU Virtualization', 'GPU 가상화')])

lab('lab_1139ae4ba42f', 'ok', 'research_intro',
    '모델 체킹·논리·SMT 기반 소프트웨어 검증, 자율 사이버물리 시스템 모델링·검증, 안전 필수 AI 소프트웨어(신경망 검증)를 연구한다.',
    [T('formal_methods', 'domain', 'we study automated algorithms for software verification, based model checking, computational logic, and satisfiability modulo theories (SMT).'),
     T('formal_methods', 'domain', 'Autonomous cyber-physical agent systems, such as self-driving cars and drones, must meet strong safety requirements.', '사이버물리 시스템 검증'),
     T('ai_safety_alignment', 'domain', 'Automated Analysis of Safety-Critical AI Software', '신경망 검증'),
     T('system_security', 'domain', 'Formal Specification of Trusted Execution Environment APIs', 'TEE·TLS 형식 명세'),
     T('embedded_systems', 'domain', 'Formal Semantics and Analysis of PLC Systems', 'PLC 시스템 의미론'),
     T('reinforcement_learning', 'method', '모델체킹을 위한 강화학습 기반 휴리스틱 학습', '모델체킹용 강화학습')])

lab('lab_fbe4dd191302', 'ok', 'research_intro',
    '햅틱 렌더링·지각을 중심으로 시각장애인용 한글 촉각 대체, XR 기반 원격 로봇 조작(공유 자율성), 소리→햅틱 자동 변환과 접근성을 연구한다.',
    [T('haptics', 'domain', 'For Ph.D, I majored in haptics with emphasis on rendering and perception'),
     T('accessibility', 'domain', 'Tactile Substitution System of Korean for Visually-Impaired Users', '시각장애인 촉각 한글'),
     T('vr_ar_xr', 'domain', 'Operating a Remote Robot in an XR Environment Based on Shared Autonomy', 'XR 원격 로봇 조작'),
     T('robotics', 'domain', 'Gesture-based control of autonomy-equipped robots', '제스처 로봇 제어'),
     T('haptics', 'domain', 'Semantic Sound-to-Haptic Automatic Conversion: Metaverse, Full-body Haptic Effects, and Accessibility', '소리-햅틱 변환'),
     T('hci', 'domain', 'Multisensory interaction methods for users in', '다감각 상호작용'),
     T('brain_neuroscience', 'domain', 'We will also study how the tactile communication for Korean will be processed in the human brain.', '촉각 인지 뇌 연구')])

lab('lab_efef6289aa4f', 'ok', 'research_intro',
    '반도체 이종집적(HI) 패키징을 위한 소재·공정(단결정 구리 배선 전기도금, AI 칩렛 열 관리, 3D BEOL)과 전기화학 기반 열전·배터리·센서 응용을 연구한다.',
    [T('semiconductor_process_packaging', 'domain', 'Our group is focusing on the advanced materials and innovative processes for heterogeneous integration (HI) technology that has attracted intensive attention in semiconductor industry.'),
     T('semiconductor_process_packaging', 'domain', 'Electrochemical synthesis of single crystal Cu for 20 nm-scaling interconnect of semiconductor device', '구리 배선 전기도금'),
     T('thermal_transport', 'domain', 'Development of thermal modeling and heat-spreading architecture for heterogeneous integrating package of AI chiplets', 'AI 칩렛 패키지 열 관리'),
     T('materials_science', 'method', 'based on nanotechnology and electrochemistry.', '전기화학·나노기술'),
     T('battery_energy', 'domain', 'including thermoelectric energy conversion, rechargeable battery, and', '열전·이차전지 응용')],
    ['진행 중 과제와 예산·협력 기관을 명시. KAIST·USC·Brookhaven 등과 협력.'])

lab('lab_e448d45da9da', 'ok', 'unclassified',
    'NPU, 근접 데이터 처리(PIM), GPU 등 대규모 병렬 구조, 데이터센터·슈퍼컴퓨터, 인터커넥트, 병렬 프로그래밍·컴파일러까지 AI·HPC를 위한 컴퓨터구조를 계층 교차 최적화한다.',
    [T('computer_architecture', 'domain', 'Neural Processing Units (NPUs)'),
     T('computer_architecture', 'domain', 'Near-data processing / processing-in-memory', 'PIM·근접 데이터 처리'),
     T('high_performance_computing', 'domain', 'Large-scale systems (datacenters and supercomputers)'),
     T('computer_architecture', 'domain', 'Massively parallel architectures (e.g., GPU)', 'GPU 구조'),
     T('networking_iot', 'domain', 'Networking / smart NICs', '스마트 NIC·인터커넥트'),
     T('compilers_programming_languages', 'domain', 'Parallel programming models / compilers'),
     T('machine_learning', 'domain', 'AI system hardware/software', 'AI 시스템 HW/SW')],
    ['Arm 근무 경력과 2025년 Arm 방문 연구 명시.'])

lab('lab_2259c59b37c3', 'ok', 'research_intro',
    '기계학습 알고리즘의 가속·실현이 목표인 효율 컴퓨팅 연구실이다. LLM 최적화(양자화·압축·PEFT·AutoML), 시각 생성모델 가속, PIM 지원, 로봇 정책 가속이 주제다.',
    [T('efficient_ai', 'domain', 'the ultimate goal is the acceleration of machine learning algorithms, but we are pleased to utilize the machine learning algorithms for acceleration.'),
     T('nlp', 'domain', 'Large Language Model (LLM) Optimization research focuses on making enormous language models more efficient, adaptable, and practical.', 'LLM 최적화'),
     T('efficient_ai', 'domain', 'AMQ introduces an AutoML-based quantization framework that automatically allocates mixed-precision bit-widths across LLM layers for optimal efficiency.', '혼합 정밀도 양자화'),
     T('generative_models', 'domain', 'Visual Generative Model Acceleration research is about speeding up image and video generation without compromising output quality.', '시각 생성모델 가속'),
     T('computer_architecture', 'domain', 'Fast and Energy-Efficient Support for Low-Precision LLMs on PIM', 'PIM 기반 LLM'),
     T('world_models_embodied', 'domain', 'Beyond image generation, PCM accelerates action policy generation in robotics, offering a pathway to real-time embodied intelligence.', '로봇 정책 가속')],
    ['ML Lab 공동 홈페이지에도 교수로 등재됨.'])

lab('lab_63c7d56c5c62', 'ok', 'research_intro',
    '컴파일러 최적화에 기계학습을 적용하고, NPU·PIM 등 신흥 구조를 위한 컴파일러·런타임, 슈퍼컴퓨터용 OpenCL 지원, 가속기 설계공간 탐색을 연구한다.',
    [T('compilers_programming_languages', 'domain', 'Machine learning for compiler optimizations'),
     T('machine_learning', 'method', 'We take data-driven approaches where the code-performance relationship is accurately learned from code representation and profiling results.'),
     T('computer_architecture', 'domain', 'We work on rethinking compiler and runtime technologies for heterogeneous systems with emerging architectures such as neural processing units (NPU) and compute-augmented memory (NDP/PIM).', 'NPU·PIM용 컴파일러'),
     T('high_performance_computing', 'domain', 'OpenCL compiler and runtime support for next-gen supercomputers'),
     T('computer_architecture', 'domain', 'Accelerator design space exploration', '가속기 설계공간 탐색')],
    ['ETRI·KISTI와 차세대 슈퍼컴퓨터 협력 명시.'])

# ---- verification and output ----
assert len(D) == len(cat.labs), (len(D), len(cat.labs))
ids = {d['lab_id'] for d in D}
assert ids == set(cat.labs), ids ^ set(cat.labs)

REVIEWS = json.load(open(ROOT / 'data/profile_reviews.json')) if (ROOT / 'data/profile_reviews.json').exists() else {}
out = []
problems = []
for d in D:
    item = cat.labs[d['lab_id']]
    members = item['members']
    sections = []
    for m in members:
        for kind, s in m.get('sections', {}).items():
            sections.append((m['professor_name'], kind, s.get('text', ''), s.get('source_urls', [])))
    topics = []
    for t in d['topics']:
        q = norm(t['quote'])
        hit = None
        if t.get('source') == 'reviewer':
            hit = (members[0]['professor_name'], 'reviewer', [members[0]['lab_url']])
        for prof, kind, text, urls in sections:
            if hit is None and q in norm(text):
                hit = (prof, kind, urls); break
        if hit is None:
            problems.append((d['lab_id'], t['quote'][:60])); continue
        weight = 'secondary' if (t['concept'] in GENERIC_METHODS and t['role'] == 'method') else 'primary'
        scope = 'application' if t['concept'] in APPLICATION.get(d['lab_id'], set()) else 'core'
        topics.append({'concept': t['concept'], 'concept_ko': concepts[t['concept']]['ko'], 'role': t['role'], 'weight': weight, 'scope': scope, 'label_ko': t['label_ko'] or concepts[t['concept']]['ko'], 'quote': t['quote'], 'section': hit[1], 'source_urls': hit[2], 'quoted_from': hit[0]})
    rv = REVIEWS.get(d['lab_id'])
    review = {'status': 'reviewed' if rv else 'assumed_ok', 'verdict': (rv or {}).get('verdict'), 'topic_verdicts': (rv or {}).get('topics', {}), 'note': (rv or {}).get('note')}
    out.append({'lab_id': d['lab_id'], 'review': review, 'professors': [m['professor_name'] for m in members], 'department': members[0]['department'], 'lab_url': members[0]['lab_url'], 'status': d['status'], 'evidence_grade': d['evidence_grade'], 'summary_ko': d['summary_ko'], 'topics': topics, 'notes': d['notes'], 'review_status': 'draft', 'drafted_by': 'Claude Fable 5.1, 2026-09-16, from collected text only'})

if problems:
    print('UNVERIFIED QUOTES:')
    for p in problems: print(' ', p)
with open(ROOT / 'data/lab_profiles.jsonl', 'w') as f:
    for row in out: f.write(json.dumps(row, ensure_ascii=False) + '\n')
import collections
print('labs', len(out), 'topics', sum(len(r['topics']) for r in out), 'status', collections.Counter(r['status'] for r in out))
print('concepts used', len({t['concept'] for r in out for t in r['topics']}), '/', len(concepts))
