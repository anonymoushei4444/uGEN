# Base container that comes with necessary packages for the framework
FROM ubuntu:22.04 AS base

# Install necessary packages including python and build tools
RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y --no-install-recommends \
    build-essential \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    libdw-dev \
    libunwind-dev \
    flex \
    bison \
    git \
    pkg-config \
    libelf-dev \
    libtraceevent-dev \
    curl 



# Set custom Rust installation paths
ENV CARGO_HOME=/usr/local/cargo
ENV RUSTUP_HOME=/usr/local/rustup
ENV PATH=$CARGO_HOME/bin:$PATH

# Install Rust using rustup
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y



# Build and install perf for correct kernel version
RUN git clone --depth 1 https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git \
 && cd linux/tools/perf \
 && NO_JEVENTS=1 make \
 && cp perf /usr/bin
# Make image smaller by removing unnecessary packages
RUN apt-get remove -y \
    bison \
    flex \
    git \
    pkg-config \
 && apt-get autoremove -y \
 && apt-get clean \
 && rm -rf linux \
 && rm -rf /var/lib/apt/lists/*

###############################################################################################
# Framework container that installs the application and its dependencies
FROM ubuntu:22.04
ARG UNAME="anonymous"
ARG UID="1001"
ARG GID="1001"

COPY --from=base / /

# Add user with specified UID and GID
RUN groupadd -g ${GID} ${UNAME} && \
    useradd -m -u ${UID} -g ${UNAME} -s /bin/bash ${UNAME}

WORKDIR /home/${UNAME}/app
USER ${UNAME}

# Create a virtual environment and install dependencies
COPY requirements.txt .

RUN pip install --upgrade pip

# RUN pip install --user --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application files
COPY app .

# Set Rust path for the non-root user
# ENV PATH="/usr/local/cargo/bin:$PATH"
# RUN /usr/local/cargo/bin/rustup default stable

CMD ["python3", "app.py"]





