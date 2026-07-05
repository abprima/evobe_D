import os
import re
from dotenv import load_dotenv
import pandas as pd
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.ticker import MaxNLocator
import matplotlib.colors as mcolors 
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
from openai import OpenAI

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD") 

engine_dfsql = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}",
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key = OPENAI_API_KEY)


# Create tabs using st.tabs()
tabs = st.tabs(["👑 CPL Achievement Report", "🚀 Melesat Generative AI" ])

# --------------------------
# Tab 1: Content
# --------------------------
with tabs[0]:
    st.subheader("📙 Head of Department Dashboard")

    st.success("""
    This dashboard enables evidence-based curriculum monitoring and Continuous Quality Improvement (CQI) by analyzing CPL achievement across all courses.
    """)

    with st.expander("🔍 Key Questions Answered"):
        st.markdown("""
    ✅ Are all Program Learning Outcomes (CPLs) being achieved?
    ✅ Which CPLs require immediate improvement?
    ✅ Which courses contribute to each CPL?
    ✅ Which courses have the lowest CPL achievement?
    ✅ Which CPLs should become the priority for CQI in the next academic cycle?
    """)

    st.write("### 👑 CPL Achievement")

    st.markdown("""This dashboard summarizes the CPL achievement of all courses within the department. Write your member code, then click **Synchronize**.""")

    unique_code = st.text_input(
        "🔑 Unique Code",
        placeholder="Write your member code here..."
    )

    # ==========================================
    # Synchronize
    # ==========================================

    if st.button("🔄 Synchronize"):

        try:

            with engine_dfsql.connect() as conn:

                member_df = pd.read_sql(
                    text("""
                        SELECT *
                        FROM member_obe
                        WHERE unique_code = :code
                        AND is_active = 1
                    """),
                    conn,
                    params={"code": unique_code}
                )

                if member_df.empty:

                    st.error("❌ Invalid Unique Code.")

                else:

                    role = member_df.loc[0, "role"]
                    department = member_df.loc[0, "department_name"]
                    full_name = member_df.loc[0, "full_name"]

                    st.success(f"👋 Welcome {full_name}... Feel free to set up  to access and review your CPL report.")

                    if role == "DH":

                        course_df = pd.read_sql(
                            text("""
                                SELECT *
                                FROM course_cpl_summary
                                WHERE department = :department
                                ORDER BY academic_year DESC,
                                        semester,
                                        course_name
                            """),
                            conn,
                            params={"department": department}
                        )

                    elif role == "DE":

                        course_df = pd.read_sql(
                            text("""
                                SELECT *
                                FROM course_cpl_summary
                                ORDER BY department,
                                        academic_year DESC,
                                        semester,
                                        course_name
                            """),
                            conn
                        )

                    # ======================================
                    # Save into Session State
                    # ======================================

                    st.session_state.course_df = course_df
                    st.session_state.department = department
                    st.session_state.role = role
                    st.session_state.full_name = full_name

        except Exception as e:

            st.error(e)

    # ==========================================
    # Dashboard
    # ==========================================

    if "course_df" in st.session_state:

        course_df = st.session_state.course_df

        # ------------------------------
        # Academic Year
        # ------------------------------

        academic_years = sorted(
            course_df["academic_year"].dropna().unique(),
            reverse=True
        )

        col1, col2 = st.columns(2)

        with col1:
            selected_year = st.selectbox(
                "📅 Academic Year",
                academic_years
            )

        # ------------------------------
        # Semester
        # ------------------------------

        semester_list = sorted(
            course_df.loc[
                course_df["academic_year"] == selected_year,
                "semester"
            ].dropna().unique()
        )

        with col2:
            selected_semester = st.selectbox(
                "🎓 Semester",
                semester_list
            )

        # ------------------------------
        # Filter
        # ------------------------------

        filtered_df = course_df[
            (course_df["academic_year"] == selected_year) &
            (course_df["semester"] == selected_semester)
        ]

        # =====================================================
        # Calculate Average CPL Achievement Across Courses
        # =====================================================

        cpl_columns = [
            col for col in filtered_df.columns
            if col.lower().startswith("cpl")
        ]

        summary_tab3 = []

        for cpl in cpl_columns:

            excellent = filtered_df.loc[
                (filtered_df["criteria"] == "Excellent") &
                (filtered_df[cpl] > 0),
                cpl
            ].mean()

            good = filtered_df.loc[
                (filtered_df["criteria"] == "Good") &
                (filtered_df[cpl] > 0),
                cpl
            ].mean()

            poor = filtered_df.loc[
                (filtered_df["criteria"] == "Poor") &
                (filtered_df[cpl] > 0),
                cpl
            ].mean()

            fail = filtered_df.loc[
                (filtered_df["criteria"] == "Fail") &
                (filtered_df[cpl] > 0),
                cpl
            ].mean()

            excellent = 0 if pd.isna(excellent) else excellent
            good = 0 if pd.isna(good) else good
            poor = 0 if pd.isna(poor) else poor
            fail = 0 if pd.isna(fail) else fail

            successful = excellent + good
            unsuccessful = poor + fail

            # Skip unused CPL
            if successful + unsuccessful == 0:
                continue

            summary_tab3.append({
                "CPL": cpl.upper(),
                "Successful": round(successful),
                "Unsuccessful": round(unsuccessful)
            })

        summary_df_tab3 = pd.DataFrame(summary_tab3)

        # ==========================================
        # Sort from Highest Intervention Priority
        # ==========================================

        summary_df_tab3["CPL_Number"] = (
            summary_df_tab3["CPL"]
            .str.extract(r"(\d+)")
            .astype(int)
        )

        summary_df_tab3 = (
            summary_df_tab3
            .sort_values("CPL_Number")
            .drop(columns="CPL_Number")
            .reset_index(drop=True)
        )

        # =====================================================
        # Department CPL Achievement Plot
        # =====================================================

        category_colors = [
            "#2196f3",   # Successful
            "#f44336"    # Unsuccessful
        ]

        def plot_department_cpl(df):

            labels = df["CPL"]

            successful = df["Successful"]

            unsuccessful = df["Unsuccessful"]

            # ======================================
            # Figure
            # ======================================

            fig, ax = plt.subplots(figsize=(9, 7))

            ax.invert_yaxis()

            ax.xaxis.set_visible(False)

            ax.set_xlim(0, 100)

            # ======================================
            # Successful
            # ======================================

            bars_success = ax.barh(
                labels,
                successful,
                height=0.8,
                color=category_colors[0],
                label="Successful",
                zorder=2
            )

            # ======================================
            # Unsuccessful
            # ======================================

            bars_fail = ax.barh(
                labels,
                unsuccessful,
                left=successful,
                height=0.8,
                color=category_colors[1],
                label="Unsuccessful",
                zorder=2
            )

            # ======================================
            # Labels
            # ======================================

            for bar in bars_success:

                width = bar.get_width()

                if width >= 5:

                    ax.text(
                        width / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{int(round(width))}",
                        ha="center",
                        va="center",
                        color="white",
                        fontsize=10,
                        fontweight="bold"
                    )

            # for bar in bars_fail:

            #     width = bar.get_width()

            #     if width >= 5:

            #         ax.text(
            #             bar.get_x() + width / 2,
            #             bar.get_y() + bar.get_height() / 2,
            #             f"{int(round(width))}",
            #             ha="center",
            #             va="center",
            #             color="white",
            #             fontsize=10,
            #             fontweight="bold"
            #         )

            # ======================================
            # Grid
            # ======================================

            ax.grid(
                which="major",
                axis="x",
                color="#DAD8D7",
                alpha=0.5,
                zorder=1
            )

            ax.grid(
                which="major",
                axis="y",
                color="#DAD8D7",
                alpha=0.5,
                zorder=1
            )

            # ======================================
            # Remove Spines
            # ======================================

            for spine in ax.spines.values():
                spine.set_visible(False)

            # ======================================
            # Top Decoration
            # ======================================

            ax.plot(
                [0.075, 0.91],
                [.98, .98],
                transform=fig.transFigure,
                clip_on=False,
                color="#2196f3",
                linewidth=1
            )

            ax.add_patch(
                plt.Rectangle(
                    (0.075, .98),
                    .15,
                    -.02,
                    transform=fig.transFigure,
                    clip_on=False,
                    facecolor="#2196f3",
                    linewidth=1
                )
            )

            # ======================================
            # Title
            # ======================================

            ax.text(
                x=0.075,
                y=0.89,
                s="CPL Achievement Report in Percentages",
                transform=fig.transFigure,
                ha="left",
                fontsize=12,
                weight="bold",
                alpha=.8
            )

            ax.text(
                x=0.075,
                y=0.855,
                s=f"{st.session_state.department} | Semester {selected_semester} {selected_year}",
                transform=fig.transFigure,
                ha="left",
                fontsize=10,
                alpha=.8
            )

            # ======================================
            # Tick Style
            # ======================================

            ax.tick_params(
                axis="y",
                labelsize=11
            )

            # ======================================
            # Legend
            # ======================================

            ax.legend(
                ncols=2,
                bbox_to_anchor=(0.5, -0.005),
                loc="upper center",
                fontsize="small",
                borderaxespad=0,
                frameon=False
            )

            # ======================================
            # Layout
            # ======================================

            plt.subplots_adjust(
                left=0.12,
                right=0.98,
                top=0.84,
                bottom=0.12
            )

            return fig


        # ======================================
        # Plot
        # ======================================

        fig = plot_department_cpl(summary_df_tab3)

        st.pyplot(fig)

        # st.dataframe(filtered_df)

        # ======================================
        # Course Contribution by CPL
        # ======================================

        available_cpl = summary_df_tab3["CPL"].tolist()

        selected_cpl = st.selectbox(
            "Select CPL to View Course Contribution",
            ["None"] + available_cpl
        )

        if selected_cpl != "None":

            selected_cpl = selected_cpl.lower()

            course_summary = []

            for course in sorted(filtered_df["course_name"].unique()):

                course_data = filtered_df[
                    filtered_df["course_name"] == course
                ]

                excellent = course_data.loc[
                    course_data["criteria"] == "Excellent",
                    selected_cpl
                ].sum()

                good = course_data.loc[
                    course_data["criteria"] == "Good",
                    selected_cpl
                ].sum()

                poor = course_data.loc[
                    course_data["criteria"] == "Poor",
                    selected_cpl
                ].sum()

                fail = course_data.loc[
                    course_data["criteria"] == "Fail",
                    selected_cpl
                ].sum()

                successful = excellent + good
                unsuccessful = poor + fail

                if successful + unsuccessful == 0:
                    continue

                course_summary.append({
                    "Course": course,
                    "Successful": round(successful),
                    "Unsuccessful": round(unsuccessful)
                })

            course_summary_df = pd.DataFrame(course_summary)

            course_summary_df = (
                course_summary_df
                .sort_values("Successful", ascending=False)
                .reset_index(drop=True)
            )

            def plot_course_cpl(df, selected_cpl):

                labels = df["Course"]

                successful = df["Successful"]

                unsuccessful = df["Unsuccessful"]

                # ======================================
                # Figure
                # ======================================

                fig, ax = plt.subplots(figsize=(9, max(5, len(labels)*0.6)))

                ax.invert_yaxis()

                ax.xaxis.set_visible(False)

                ax.set_xlim(0,100)

                # ======================================
                # Successful
                # ======================================

                bars_success = ax.barh(
                    labels,
                    successful,
                    height=0.8,
                    color="#2196f3",
                    label="Successful",
                    zorder=2
                )

                # ======================================
                # Unsuccessful
                # ======================================

                bars_fail = ax.barh(
                    labels,
                    unsuccessful,
                    left=successful,
                    height=0.8,
                    color="#f44336",
                    label="Unsuccessful",
                    zorder=2
                )

                # ======================================
                # Labels
                # ======================================

                for bar in bars_success:

                    width = bar.get_width()

                    if width >= 5:

                        ax.text(
                            width/2,
                            bar.get_y()+bar.get_height()/2,
                            f"{int(round(width))}",
                            ha="center",
                            va="center",
                            color="white",
                            fontsize=10,
                            fontweight="bold"
                        )

                # Uncomment if you also want labels in red bar

                # for bar in bars_fail:
                #
                #     width = bar.get_width()
                #
                #     if width >= 5:
                #
                #         ax.text(
                #             bar.get_x()+width/2,
                #             bar.get_y()+bar.get_height()/2,
                #             f"{int(round(width))}",
                #             ha="center",
                #             va="center",
                #             color="white",
                #             fontsize=10,
                #             fontweight="bold"
                #         )

                # ======================================
                # Grid
                # ======================================

                ax.grid(
                    which="major",
                    axis="x",
                    color="#DAD8D7",
                    alpha=.5,
                    zorder=1
                )

                ax.grid(
                    which="major",
                    axis="y",
                    color="#DAD8D7",
                    alpha=.5,
                    zorder=1
                )

                # ======================================
                # Remove Spines
                # ======================================

                for spine in ax.spines.values():
                    spine.set_visible(False)

                # ======================================
                # Top Decoration
                # ======================================

                ax.plot(
                    [0.075,0.91],
                    [.98,.98],
                    transform=fig.transFigure,
                    clip_on=False,
                    color="#2196f3",
                    linewidth=1
                )

                ax.add_patch(
                    plt.Rectangle(
                        (0.075,.98),
                        .15,
                        -.02,
                        transform=fig.transFigure,
                        clip_on=False,
                        facecolor="#2196f3",
                        linewidth=1
                    )
                )

                # ======================================
                # Title
                # ======================================

                ax.text(
                    x=0.075,
                    y=0.89,
                    s=f"Course Contribution to {selected_cpl.upper()}",
                    transform=fig.transFigure,
                    ha="left",
                    fontsize=12,
                    weight="bold",
                    alpha=.8
                )

                ax.text(
                    x=0.075,
                    y=0.855,
                    s=f"{st.session_state.department} | Semester {selected_semester} {selected_year}",
                    transform=fig.transFigure,
                    ha="left",
                    fontsize=10,
                    alpha=.8
                )

                # ======================================
                # Tick Style
                # ======================================

                ax.tick_params(
                    axis="y",
                    labelsize=10
                )

                # ======================================
                # Legend
                # ======================================

                ax.legend(
                    ncols=2,
                    bbox_to_anchor=(0.5,-0.005),
                    loc="upper center",
                    fontsize="small",
                    borderaxespad=0,
                    frameon=False
                )

                # ======================================
                # Layout
                # ======================================

                plt.subplots_adjust(
                    left=0.25,
                    right=0.98,
                    top=0.84,
                    bottom=0.12
                )

                return fig

            fig = plot_course_cpl(course_summary_df, selected_cpl)
            st.pyplot(fig)


    else:

        st.info("👆 Please enter your unique code and click **Synchronize**.")

# --------------------------
# Tab 2
# --------------------------
with tabs[1]:


    st.write("### 🚀 Melesat Generative AI")
    st.success(
        """
    Select the type of analysis you want the AI to perform.
    The system will automatically retrieve the required data
    from the database and prepare it for AI analysis.
    """)

    st.divider()

    # ==========================================================
    # Initialize Session State
    # ==========================================================

    if "ai_datasets" not in st.session_state:
        st.session_state.ai_datasets = {}

    if "analysis_scope" not in st.session_state:
        st.session_state.analysis_scope = None

    # ==========================================================
    # Analysis Scope
    # ==========================================================

    st.subheader("ðŸ“Š Analysis Scope")

    analysis_scope = st.radio(
        "Choose Analysis Type",
        [
            "Student CPMK/CPL Performance",
            "CPMK Ã— CPL Mapping Analysis",
            "Comprehensive Analysis"
        ],
        horizontal=True
    )

    # ==========================================================
    # Academic Year
    # ==========================================================

    with engine_dfsql.connect() as conn:

        year_df = pd.read_sql(
            text("""
                SELECT DISTINCT academic_year
                FROM course_cpl_summary
                ORDER BY academic_year DESC
            """),
            conn
        )

    selected_year = st.selectbox(
        "Academic Year",
        year_df["academic_year"]
    )

    # ==========================================================
    # Semester
    # ==========================================================

    with engine_dfsql.connect() as conn:

        semester_df = pd.read_sql(
            text("""
                SELECT DISTINCT semester
                FROM course_cpl_summary
                WHERE academic_year=:year
                ORDER BY semester
            """),
            conn,
            params={
                "year": selected_year
            }
        )

    selected_semester = st.selectbox(
        "Semester",
        semester_df["semester"]
    )

    # ==========================================================
    # Load Dataset
    # ==========================================================

    if st.button(
        "ðŸ“¥ Load Dataset",
        use_container_width=True
    ):

        datasets = {}

        with st.spinner("Loading dataset from MySQL..."):

            with engine_dfsql.connect() as conn:

                # ==============================================
                # Student CPMK/CPL Performance
                # ==============================================

                if analysis_scope == "Student CPMK/CPL Performance":

                    student_df = pd.read_sql(

                        text("""

                        SELECT *
                        FROM student_cpmk_result
                        WHERE department=:department
                        AND academic_year=:academic_year
                        AND semester=:semester
                        ORDER BY course_name,
                                 student_name

                        """),

                        conn,

                        params={

                            "department": st.session_state.department,
                            "academic_year": selected_year,
                            "semester": selected_semester

                        }

                    )

                    datasets["student"] = student_df

                # ==============================================
                # CPMK Ã— CPL Mapping
                # ==============================================

                elif analysis_scope == "CPMK Ã— CPL Mapping Analysis":

                    course_df = pd.read_sql(

                        text("""

                        SELECT *
                        FROM course_cpl_summary
                        WHERE department=:department
                        AND academic_year=:academic_year
                        AND semester=:semester
                        ORDER BY course_name

                        """),

                        conn,

                        params={

                            "department": st.session_state.department,
                            "academic_year": selected_year,
                            "semester": selected_semester

                        }

                    )

                    datasets["course"] = course_df

                # ==============================================
                # Comprehensive Analysis
                # ==============================================

                else:

                    course_df = pd.read_sql(

                        text("""

                        SELECT *
                        FROM course_cpl_summary
                        WHERE department=:department
                        AND academic_year=:academic_year
                        AND semester=:semester
                        ORDER BY course_name

                        """),

                        conn,

                        params={

                            "department": st.session_state.department,
                            "academic_year": selected_year,
                            "semester": selected_semester

                        }

                    )

                    student_df = pd.read_sql(

                        text("""

                        SELECT *
                        FROM student_cpmk_result
                        WHERE department=:department
                        AND academic_year=:academic_year
                        AND semester=:semester
                        ORDER BY course_name,
                                 student_name

                        """),

                        conn,

                        params={

                            "department": st.session_state.department,
                            "academic_year": selected_year,
                            "semester": selected_semester

                        }

                    )

                    datasets["course"] = course_df
                    datasets["student"] = student_df

        st.session_state.ai_datasets = datasets
        st.session_state.analysis_scope = analysis_scope

        st.success("Dataset successfully loaded.")

    # ==========================================================
    # Dataset Preview
    # ==========================================================

    if st.session_state.ai_datasets:

        st.divider()

        st.subheader("ðŸ“‹ Dataset Preview")

        for dataset_name, df in st.session_state.ai_datasets.items():

            with st.expander(
                f"{dataset_name.upper()} ({len(df):,} rows)",
                expanded=True
            ):

                col1, col2 = st.columns(2)

                col1.metric("Rows", len(df))
                col2.metric("Columns", len(df.columns))

                st.dataframe(
                    df.head(20),
                    use_container_width=True,
                    hide_index=True
                )

        st.success(
            "The selected dataset(s) are ready. In Part 2B, they will be converted "
            "into AI context and sent to the OpenAI API for conversational analysis."
        )