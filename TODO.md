# TODO — release signing

Plan for signing the release artifacts that `.github/workflows/build-release.yml`
attaches to GitHub releases. Linux is actionable now; Windows and macOS are
written up but blocked on purchasing credentials.

---

## 1. Linux: GPG-sign release artifacts (actionable now)

Goal: every Linux artifact (`.tar.gz`, `.deb`, `.rpm`, `.pkg.tar.zst`) ships
with a detached GPG signature plus a signed `SHA256SUMS` file, so users can
verify downloads came from this project.

### 1.1 One-time setup (maintainer machine)

- [ ] Generate a dedicated release-signing key (keep it separate from any
      personal key so it can be revoked/rotated independently):

      gpg --quick-generate-key \
          "PyMappr Release Signing <calebahendren@gmail.com>" ed25519 sign 2y

- [ ] Export and record:

      gpg --armor --export "PyMappr Release Signing"        > packaging/pymappr-release-key.asc
      gpg --armor --export-secret-keys "PyMappr Release Signing"   # -> secret, do NOT commit

- [ ] Commit the **public** key as `packaging/pymappr-release-key.asc` and
      note its fingerprint in the README's install section (the one allowed
      README mention: how users verify downloads).
- [ ] Optionally publish the public key to `keys.openpgp.org`.
- [ ] Add GitHub Actions repository secrets (Settings → Secrets → Actions):
      - `GPG_PRIVATE_KEY` — the armored secret key export
      - `GPG_PASSPHRASE` — its passphrase

### 1.2 Workflow changes (`.github/workflows/build-release.yml`)

- [ ] In the `release` job, after "Download all build artifacts" and the
      source archive step, add a signing step (secrets are only exposed to
      this job; the per-OS build jobs stay credential-free):

      - name: Import release signing key
        env:
          GPG_PRIVATE_KEY: ${{ secrets.GPG_PRIVATE_KEY }}
          GPG_PASSPHRASE: ${{ secrets.GPG_PASSPHRASE }}
        run: |
          printf '%s' "$GPG_PRIVATE_KEY" | gpg --batch --import
          echo "allow-preset-passphrase" >> ~/.gnupg/gpg-agent.conf

      - name: Sign release artifacts
        env:
          GPG_PASSPHRASE: ${{ secrets.GPG_PASSPHRASE }}
        working-directory: release-assets
        run: |
          sha256sum * > SHA256SUMS
          gpg --batch --yes --pinentry-mode loopback \
              --passphrase "$GPG_PASSPHRASE" \
              --clearsign --output SHA256SUMS.asc SHA256SUMS
          for f in *.tar.gz *.deb *.rpm *.pkg.tar.zst *.zip; do
            [ -e "$f" ] || continue
            gpg --batch --yes --pinentry-mode loopback \
                --passphrase "$GPG_PASSPHRASE" \
                --armor --detach-sign "$f"
          done

- [ ] `files: release-assets/**` already uploads everything, so the new
      `SHA256SUMS`, `SHA256SUMS.asc`, and `*.asc` files attach automatically.
      Keep `fail_on_unmatched_files: true`.
- [ ] Verify one release end-to-end:

      gpg --import pymappr-release-key.asc
      gpg --verify SHA256SUMS.asc && sha256sum -c SHA256SUMS
      gpg --verify pymappr_1.6.1_amd64.deb.asc pymappr_1.6.1_amd64.deb

### 1.3 Format-native signatures (phase 2, optional)

Detached `.asc` files cover every format uniformly. Native embedding can come
later:

- [ ] **RPM**: embed the signature so `rpm -K` passes — add `rpm-sign` to the
      fedora container, import the key, and run
      `rpmsign --define "_gpg_name PyMappr Release Signing" --addsign dist/pymappr-*.rpm`
      (requires moving signing into the `build-fedora` job or re-signing in
      `release`, where `rpmsign` is available via the `rpm` apt package).
- [ ] **Arch**: `.sig` detached signatures are already the native convention;
      renaming `.asc` → binary `.sig` (`gpg --detach-sign`, no `--armor`)
      makes `pacman-key`-based verification possible.
- [ ] **Debian**: per-file `.asc` is fine for direct downloads. A proper apt
      repository with a signed `Release` file is only worth it if we start
      hosting one.

### 1.4 Provenance attestations (phase 2, optional, no secrets needed)

- [ ] Add GitHub build-provenance attestations — complementary to GPG,
      keyless, and verifiable with the `gh` CLI:

      permissions:
        id-token: write
        attestations: write

      - uses: actions/attest-build-provenance@v2
        with:
          subject-path: release-assets/*

      Users verify with `gh attestation verify <file> -R CalebHendren/PyMappr`.

---

## 2. Windows: Authenticode code signing (blocked — needs a certificate)

Unsigned installers trip SmartScreen ("Windows protected your PC"). Blocked
until a signing identity is purchased.

- [ ] Pick an identity (decision needed):
      - **Azure Trusted Signing** (~$10/month) — cheapest, cloud HSM, integrates
        with GitHub Actions via `azure/trusted-signing-action`; requires an
        Azure tenant and identity validation.
      - **OV certificate on HSM/token** (Certum/Sectigo/SSL.com, ~$70–300/yr) —
        since June 2023 keys must live on hardware or a cloud HSM, so plain
        `.pfx`-in-a-secret is no longer an option; use the CA's cloud signing
        service (e.g. SSL.com eSigner) from CI.
      - SmartScreen reputation builds over time with OV; EV starts trusted but
        costs more.
- [ ] Add the CA-specific secrets (tenant/API key/credentials per the chosen
      service) to GitHub Actions.
- [ ] Sign **both** the app and the installer in `build-windows`:
      1. after PyInstaller: sign `dist/PyMappr/PyMappr.exe`
      2. let Inno Setup sign the setup + uninstaller: define a `SignTool` in
         `installer.iss` (`SignTool=mysign $f`) and pass the tool definition
         on the `ISCC.exe` command line (`/Smysign=...`), or sign
         `dist/installer/PyMappr-Setup-*.exe` as a separate step afterwards.
      Always use the RFC 3161 timestamp server of the CA so signatures outlive
      the certificate.
- [ ] Verify in CI: `signtool verify /pa /v dist/installer/PyMappr-Setup-*.exe`.

---

## 3. macOS: codesign + notarization (blocked — needs Apple Developer Program)

Unsigned apps are blocked by Gatekeeper with "cannot be opened because the
developer cannot be verified". Blocked until an Apple Developer membership
($99/yr) is available.

- [ ] Enroll in the Apple Developer Program; create a **Developer ID
      Application** certificate; export it as `.p12`.
- [ ] Create an App Store Connect API key (or an app-specific password) for
      `notarytool`.
- [ ] GitHub Actions secrets: `MACOS_CERT_P12` (base64), `MACOS_CERT_PASSWORD`,
      `NOTARY_KEY_ID`, `NOTARY_ISSUER_ID`, `NOTARY_KEY` (the `.p8`).
- [ ] In `build-macos`, after PyInstaller and before the DMG step:
      1. import the cert into a throwaway keychain
         (`security create-keychain` … `security import` …);
      2. sign the bundle with hardened runtime — PyInstaller apps need
         inside-out signing of every dylib/binary, which
         `codesign --force --deep --options runtime --timestamp` handles for
         our simple bundle (revisit `--deep` if entitlements are ever needed;
         Tk/matplotlib need none today);
      3. build the DMG (existing step), then sign it too;
      4. `xcrun notarytool submit dist/PyMappr-*-macOS.dmg --wait` with the
         API key, then `xcrun stapler staple` the DMG;
      5. smoke-check: `spctl -a -t open --context context:primary-signature -v`
         on the DMG and `codesign --verify --deep --strict` on the app.
- [ ] Consider `pyinstaller --codesign-identity` as a simpler alternative for
      step 2 (PyInstaller signs the bundle contents itself at build time).

---

## Notes

- Secrets must never be echoed in workflow logs; all snippets above pass them
  via `env:`/action inputs only.
- Rotate the GPG key before its 2-year expiry; publish the new public key one
  release ahead so users can update.
