<#
.SYNOPSIS
    Authenticode-sign a Loudmouth artifact via Azure Artifact Signing
    (Trusted Signing). No-op with a warning when signing is not configured,
    so internal/fleet builds stay unsigned without failing the build.

.DESCRIPTION
    Signing policy (sprint brief §2.2):
      - Azure Artifact Signing (~$10/mo), not a traditional OV cert.
      - Sign BOTH layers: loudmouth.exe and LoudmouthSetup-<ver>.exe.
      - Timestamp every signature.
      - Build from clean CI, never a developer workstation.
      - Unsigned builds are fine for internal testing; sign from first
        external beta.

    Configuration (all required to enable signing):
      LOUDMOUTH_SIGN_ENDPOINT     e.g. https://eus.codesigning.azure.net
      LOUDMOUTH_SIGN_ACCOUNT      Trusted Signing account name
      LOUDMOUTH_SIGN_PROFILE      certificate profile name
    Plus Azure credentials in the environment (AZURE_TENANT_ID,
    AZURE_CLIENT_ID, AZURE_CLIENT_SECRET — or managed identity in CI).

    Requires the Azure.CodeSigning signtool dlib. In CI, use the
    azure/trusted-signing-action instead of this script (see
    .github/workflows/release.yml); this script is the local/manual path.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = "Stop"

$endpoint = $env:LOUDMOUTH_SIGN_ENDPOINT
$account  = $env:LOUDMOUTH_SIGN_ACCOUNT
$profile_ = $env:LOUDMOUTH_SIGN_PROFILE

if (-not ($endpoint -and $account -and $profile_)) {
    Write-Warning "Signing not configured (LOUDMOUTH_SIGN_* env unset) - leaving '$Path' UNSIGNED. OK for internal builds; required from first external beta."
    exit 0
}

# Trusted Signing signs via signtool + the Azure.CodeSigning dlib.
# Install once:  dotnet tool install --global azuresigntool  (alternative)
# or download Microsoft.Trusted.Signing.Client and point at its dlib:
$dlib = $env:LOUDMOUTH_SIGN_DLIB
if (-not $dlib) { throw "LOUDMOUTH_SIGN_DLIB must point at Azure.CodeSigning.Dlib.dll" }

$metadata = @{
    Endpoint               = $endpoint
    CodeSigningAccountName = $account
    CertificateProfileName = $profile_
} | ConvertTo-Json
$metadataFile = Join-Path $env:TEMP "loudmouth-signing-metadata.json"
$metadata | Out-File -Encoding ascii $metadataFile

Write-Host "-- Signing $Path (Azure Trusted Signing, RFC3161 timestamp)" -ForegroundColor Cyan
signtool sign /v /fd SHA256 /tr "http://timestamp.acs.microsoft.com" /td SHA256 `
    /dlib $dlib /dmdf $metadataFile $Path
if ($LASTEXITCODE -ne 0) { throw "signtool failed for $Path" }

signtool verify /pa /v $Path
if ($LASTEXITCODE -ne 0) { throw "signature verification failed for $Path" }
