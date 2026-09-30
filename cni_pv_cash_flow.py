import streamlit as st
import numpy_financial as npf
import pandas as pd
import io

# --- PAGE SETUP ---
st.set_page_config(page_title="Indian C&I Solar Modeler", layout="wide", page_icon="🇮🇳")

# --- SIDEBAR: PROJECT & MODEL SETUP ---
st.sidebar.header("1. Project Details")
project_name = st.sidebar.text_input("Project Name", value="Maha-Solar Group Captive I")
currency = st.sidebar.selectbox("Currency", ["₹ (INR)", "$ (USD)"])
sym = currency.split(" ")[0]

st.sidebar.header("2. Business & Ownership Model")
siting = st.sidebar.radio("Project Siting", ["On-Site (Rooftop/Ground)", "Off-Site (Open Access)"])
ownership = st.sidebar.selectbox("Ownership Structure", ["Group Captive", "Captive (100% Consumer)", "Third-Party PPA"])

# Group Captive Rules Enforcement
consumer_equity_pct = 100
consumer_offtake_pct = 100
if ownership == "Group Captive":
    st.sidebar.caption("⚡ Electricity Act 2003 Rules")
    consumer_equity_pct = st.sidebar.slider("Consumer Equity Share (%)", 0, 100, 26)
    consumer_offtake_pct = st.sidebar.slider("Power Consumed by Consumer (%)", 0, 100, 100)
elif ownership == "Third-Party PPA":
    consumer_equity_pct = 0

developer_equity_pct = 100 - consumer_equity_pct

# --- SIDEBAR: OPEN ACCESS CHARGES ---
wheeling_charge, transmission_charge, sldc_charge, css, additional_surcharge = 0.0, 0.0, 0.0, 0.0, 0.0
grid_losses, banking_charge = 0.0, 0.0

if siting == "Off-Site (Open Access)":
    st.sidebar.header("3. Open Access Charges (per kWh)")
    wheeling_charge = st.sidebar.number_input(f"Wheeling Charge ({sym})", value=0.60, step=0.05)
    transmission_charge = st.sidebar.number_input(f"Transmission Charge ({sym})", value=0.40, step=0.05)
    sldc_charge = st.sidebar.number_input(f"SLDC / Other ({sym})", value=0.05, step=0.01)
    
    if ownership == "Third-Party PPA":
        css = st.sidebar.number_input(f"Cross Subsidy Surcharge (CSS) ({sym})", value=1.50, step=0.10)
        additional_surcharge = st.sidebar.number_input(f"Additional Surcharge (AS) ({sym})", value=0.80, step=0.10)
    else:
        st.sidebar.success("✅ CSS and AS waived for Captive/Group Captive.")
        
    grid_losses = st.sidebar.number_input("State Grid Losses (%)", value=3.5, step=0.5) / 100
    banking_charge = st.sidebar.number_input("Banking Charges (%)", value=2.0, step=0.5) / 100

# --- SIDEBAR: ASSET & FINANCING ---
st.sidebar.header("4. Asset & Financing")
capacity_kw = st.sidebar.number_input("System Capacity (kW)", value=5000)
capex_per_kw = st.sidebar.number_input(f"Capex per kW ({sym})", value=45000)
total_capex = capacity_kw * capex_per_kw

debt_pct = st.sidebar.slider("Debt-to-Equity Ratio (%)", 0, 100, 70) / 100
debt_principal = total_capex * debt_pct
total_equity = total_capex - debt_principal
interest_rate = st.sidebar.number_input("Term Loan Interest Rate (%)", value=8.5, step=0.1) / 100
loan_term_years = st.sidebar.number_input("Loan Tenor (Years)", value=10, step=1)
moratorium_years = st.sidebar.number_input("Principal Moratorium (Years)", value=1, step=1)

# --- SIDEBAR: TARIFFS & TAX ---
st.sidebar.header("5. Tariffs & Tax")
cuf = st.sidebar.number_input("Plant CUF (%)", value=19.0, step=0.5) / 100
degradation = st.sidebar.number_input("Annual Degradation (%)", value=0.5, step=0.1) / 100
ppa_tariff = st.sidebar.number_input(f"Base PPA Tariff ({sym}/kWh)", value=4.00, step=0.1)
discom_tariff = st.sidebar.number_input(f"Current DISCOM Tariff ({sym}/kWh)", value=8.50, step=0.25)
discom_escalation = st.sidebar.number_input("DISCOM Annual Escalation (%)", value=3.0, step=0.5) / 100

tax_rate = st.sidebar.number_input("Corporate Tax Rate (%)", value=25.17, step=1.0) / 100
apply_ad = st.sidebar.checkbox("Apply Accelerated Depreciation (40% WDV)", value=True)

# --- CORE CALCULATIONS (15-Year Annual Model) ---
years = 15
table_data = []
net_project_cfs = [-total_capex]
developer_cfs = [-(total_equity * (developer_equity_pct / 100))]
consumer_cfs = [-(total_equity * (consumer_equity_pct / 100))]

wdv = total_capex
outstanding_debt = debt_principal
annual_opex = capacity_kw * 500  # Assuming 500 INR/kW/year O&M base

for y in range(1, years + 1):
    # Generation & Losses
    generated_kwh = capacity_kw * 8760 * cuf * ((1 - degradation) ** (y - 1))
    delivered_kwh = generated_kwh * (1 - grid_losses - banking_charge)
    consumer_offtake_kwh = delivered_kwh * (consumer_offtake_pct / 100)
    
    # Tariffs & Revenue
    current_discom_tariff = discom_tariff * ((1 + discom_escalation) ** (y - 1))
    revenue = delivered_kwh * ppa_tariff
    
    # Landed Cost & Savings
    oa_charges_per_kwh = wheeling_charge + transmission_charge + sldc_charge + css + additional_surcharge
    landed_cost_per_kwh = ppa_tariff + oa_charges_per_kwh
    total_landed_cost = landed_cost_per_kwh * consumer_offtake_kwh
    avoided_discom_cost = current_discom_tariff * consumer_offtake_kwh
    consumer_savings = avoided_discom_cost - total_landed_cost
    
    # Opex
    current_opex = annual_opex * ((1 + 0.05) ** (y - 1)) # 5% O&M Escalation
    ebitda = revenue - current_opex
    
    # Debt Service
    interest_paid = outstanding_debt * interest_rate
    if y <= moratorium_years:
        principal_paid = 0
    else:
        remaining_years = loan_term_years - moratorium_years
        pmt = -npf.pmt(interest_rate, remaining_years, debt_principal) if y <= loan_term_years else 0
        principal_paid = pmt - interest_paid if y <= loan_term_years else 0
    
    debt_service = principal_paid + interest_paid
    outstanding_debt -= principal_paid
    
    # Tax & Depreciation
    depreciation = (wdv * 0.40) if apply_ad else (total_capex / 25) # 40% WDV vs Straight Line
    wdv -= depreciation
    taxable_income = max(0, ebitda - interest_paid - depreciation)
    tax_paid = taxable_income * tax_rate
    
    # Cash Flows
    cfads = ebitda - tax_paid
    net_cf = cfads - debt_service
    dscr = cfads / debt_service if debt_service > 0 else 0
    
    # Split Cash Flows
    dev_cash_flow = net_cf * (developer_equity_pct / 100)
    cons_cash_flow = consumer_savings + (net_cf * (consumer_equity_pct / 100))
    
    net_project_cfs.append(net_cf)
    developer_cfs.append(dev_cash_flow)
    consumer_cfs.append(cons_cash_flow)
    
    table_data.append({
        "Year": f"Year {y}",
        "Delivered (kWh)": delivered_kwh,
        "DISCOM Tariff": current_discom_tariff,
        "Landed Cost": landed_cost_per_kwh,
        "Revenue": revenue,
        "Opex": current_opex,
        "EBITDA": ebitda,
        "Debt Service": debt_service,
        "Tax Paid": tax_paid,
        "Net Cash Flow": net_cf,
        "DSCR": dscr,
        "Consumer Savings": consumer_savings
    })

df = pd.DataFrame(table_data)

# Calculate IRRs
proj_irr = npf.irr(net_project_cfs) * 100 if not pd.isna(npf.irr(net_project_cfs)) else 0
dev_irr = npf.irr(developer_cfs) * 100 if developer_equity_pct > 0 else 0
cons_irr = npf.irr(consumer_cfs) * 100 if consumer_equity_pct > 0 else "N/A (No Equity)"

# --- DASHBOARD UI ---
st.title(f"🇮🇳 {project_name}")
st.subheader("C&I Solar Financial Structuring Dashboard")

# Warnings for Group Captive
if ownership == "Group Captive":
    if consumer_equity_pct < 26:
        st.error("⚠️️ RULE VIOLATION: Under the Electricity Act 2003, captive users must hold a minimum of 26% equity.")
    if consumer_offtake_pct < 51:
        st.error("⚠️ RULE VIOLATION: Captive users must consume at least 51% of the aggregate electricity generated.")

# Top Metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Project Unlevered IRR", f"{proj_irr:.2f}%")
col2.metric("Developer Equity IRR", f"{dev_irr:.2f}%" if type(dev_irr) == float else dev_irr)
col3.metric("Consumer ROI (IRR)", f"{cons_irr:.2f}%" if type(cons_irr) == float else cons_irr)
col4.metric("Year 1 Landed Cost", f"{sym}{df.iloc[0]['Landed Cost']:.2f} / kWh")

st.divider()

# Tabs for organization
tab1, tab2, tab3 = st.tabs(["📊 Value Proposition (Graphs)", "🏢 Financial Waterfall", "⚙️ Capital Stack"])

with tab1:
    st.subheader("Consumer Savings: Landed Cost vs DISCOM Tariff")
    chart_df = df.set_index("Year")[["DISCOM Tariff", "Landed Cost"]]
    st.line_chart(chart_df)
    
    st.subheader("Project Cash Flow Profile")
    cf_chart = df.set_index("Year")[["Revenue", "EBITDA", "Net Cash Flow"]]
    st.bar_chart(cf_chart)

with tab2:
    st.subheader("15-Year Financial Waterfall")
    format_dict = {
        "Delivered (kWh)": "{:,.0f}",
        "DISCOM Tariff": f"{sym}{{:,.2f}}",
        "Landed Cost": f"{sym}{{:,.2f}}",
        "Revenue": f"{sym}{{:,.0f}}",
        "Opex": f"{sym}{{:,.0f}}",
        "EBITDA": f"{sym}{{:,.0f}}",
        "Debt Service": f"{sym}{{:,.0f}}",
        "Tax Paid": f"{sym}{{:,.0f}}",
        "Net Cash Flow": f"{sym}{{:,.0f}}",
        "DSCR": "{:.2f}x",
        "Consumer Savings": f"{sym}{{:,.0f}}"
    }
    st.dataframe(df.style.format(format_dict), use_container_width=True)
    
    # Excel Export
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='C&I Model', index=False)
    
    st.download_button(
        label=f"📥 Download Full Model for {project_name} (Excel)",
        data=buffer.getvalue(),
        file_name=f"{project_name.replace(' ', '_')}_Model.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

with tab3:
    st.subheader("Capital Structure")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Project Capex", f"{sym}{total_capex:,.0f}")
    c2.metric(f"Senior Debt ({debt_pct*100:.0f}%)", f"{sym}{debt_principal:,.0f}")
    c3.metric(f"Total Equity ({(1-debt_pct)*100:.0f}%)", f"{sym}{total_equity:,.0f}")
    
    if ownership == "Group Captive":
        st.info(f"**Group Captive Equity Split:** Developer provides {sym}{total_equity * (developer_equity_pct/100):,.0f} | Consumer provides {sym}{total_equity * (consumer_equity_pct/100):,.0f}")
