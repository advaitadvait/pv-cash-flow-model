import streamlit as st
import numpy_financial as npf
import pandas as pd
import io

# Set page configuration
st.set_page_config(page_title="PV Cash Flow & Graphing", layout="wide", page_icon="☀️")

# --- SIDEBAR: PROJECT DETAILS & CURRENCY ---
st.sidebar.header("Project Details")
project_name = st.sidebar.text_input("Project Name", value="Solar Asset Alpha")
currency_option = st.sidebar.selectbox("Currency", ["₹ (INR)", "$ (USD)", "€ (EUR)", "£ (GBP)"])
sym = currency_option.split(" ")[0] # Extracts just the symbol (₹, $, etc.)

# Update Title dynamically based on project name
st.title(f"☀️ {project_name} - Cash Flow & Debt Service")

# --- SIDEBAR: ASSET ASSUMPTIONS ---
st.sidebar.header("Asset & Financing Inputs")
# Scaled default values up slightly to be more realistic for INR
initial_investment = st.sidebar.number_input(f"Total Capex / Asset PV ({sym})", value=10000000.0, step=100000.0)
debt_principal = st.sidebar.number_input(f"Senior Debt Principal ({sym})", value=7000000.0, step=100000.0)
interest_rate = st.sidebar.number_input("Annual Interest Rate (%)", value=8.5) / 100
loan_term_years = st.sidebar.number_input("Tenor / Loan Term (Years)", value=7, step=1)

st.sidebar.header("Operations & Solar Yield")
base_annual_revenue = st.sidebar.number_input(f"Base Annual Revenue / PPA ({sym})", value=2500000.0, step=50000.0)
annual_growth_rate = st.sidebar.number_input("Escalation / Growth Rate (%)", value=2.5) / 100
base_annual_opex = st.sidebar.number_input(f"Annual O&M / Opex ({sym})", value=400000.0, step=10000.0)

st.sidebar.subheader("Quarterly Solar Generation Profile")
st.sidebar.caption("Adjust weights to reflect seasonal solar irradiance (averages ~1.0):")
q1 = st.sidebar.slider("Q1 Generation (Winter/Spring)", 0.4, 1.6, 0.8)
q2 = st.sidebar.slider("Q2 Generation (Spring/Summer)", 0.4, 1.6, 1.3)
q3 = st.sidebar.slider("Q3 Generation (Summer/Fall)", 0.4, 1.6, 1.2)
q4 = st.sidebar.slider("Q4 Generation (Fall/Winter)", 0.4, 1.6, 0.7)
seasonality = [q1, q2, q3, q4]

# --- FINANCIAL LOGIC ---
quarters = 5 * 4  
quarterly_rate = interest_rate / 4
total_periods = loan_term_years * 4
quarterly_debt_service = -npf.pmt(quarterly_rate, total_periods, debt_principal)

table_data = []
net_cash_flows = [-initial_investment]
total_cfads = 0
total_debt_service = 0

for q in range(1, quarters + 1):
    year_index = (q - 1) // 4
    quarter_index = (q - 1) % 4
    
    current_year_revenue = base_annual_revenue * ((1 + annual_growth_rate) ** year_index)
    quarterly_revenue = (current_year_revenue / 4) * seasonality[quarter_index]
    
    current_year_opex = base_annual_opex * ((1 + annual_growth_rate) ** year_index)
    quarterly_opex = current_year_opex / 4
    
    cfads = quarterly_revenue - quarterly_opex
    net_cf = cfads - quarterly_debt_service
    dscr = cfads / quarterly_debt_service if quarterly_debt_service > 0 else 0
    
    net_cash_flows.append(net_cf)
    total_cfads += cfads
    total_debt_service += quarterly_debt_service
    
    table_data.append({
        "Quarter": f"Y{year_index + 1} Q{quarter_index + 1}",
        "Revenue (PPA)": quarterly_revenue,
        "O&M / Opex": quarterly_opex,
        "CFADS": cfads,
        "Debt Service": quarterly_debt_service,
        "Net Cash Flow": net_cf,
        "DSCR": dscr
    })

df = pd.DataFrame(table_data)

# Calculate Key Financial Metrics
quarterly_irr = npf.irr(net_cash_flows)
annualized_irr = ((1 + quarterly_irr) ** 4 - 1) if not pd.isna(quarterly_irr) else 0
average_dscr = total_cfads / total_debt_service if total_debt_service > 0 else 0

# --- DASHBOARD METRICS ---
col1, col2, col3 = st.columns(3)
col1.metric("Project IRR (Annualized)", f"{annualized_irr * 100:.2f}%")
col2.metric("Average DSCR", f"{average_dscr:.2f}x")
col3.metric("5-Year Total CFADS", f"{sym}{total_cfads:,.0f}")

st.divider()

# --- CHARTS & WATERFALL TABLE ---
st.subheader("Solar Revenue & CFADS vs Senior Debt Service")
chart_data = df.set_index("Quarter")[["Revenue (PPA)", "CFADS"]]
st.bar_chart(chart_data)

st.subheader("5-Year Quarterly Financial Waterfall")

# Dynamically apply the selected currency symbol to the formatting
format_dict = {
    "Revenue (PPA)": f"{sym}{{:,.2f}}", 
    "O&M / Opex": f"{sym}{{:,.2f}}", 
    "CFADS": f"{sym}{{:,.2f}}", 
    "Debt Service": f"{sym}{{:,.2f}}", 
    "Net Cash Flow": f"{sym}{{:,.2f}}", 
    "DSCR": "{:.2f}x"
}
st.dataframe(df.style.format(format_dict), use_container_width=True)

# --- EXCEL EXPORT ---
# Convert dataframe to an Excel file in memory
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='Cash Flow', index=False)

# Add a download button at the bottom of the app
st.download_button(
    label=f"📥 Download {project_name} Calculations (Excel)",
    data=buffer.getvalue(),
    file_name=f"{project_name.replace(' ', '_')}_Cash_Flow.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
