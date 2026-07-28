/*
 * Drill-down for a single program (the Friday target). Opens from the tests table.
 * Structure:
 *   1. Header: program name + status, with the run's RTL dir / mutation label.
 *   2. Lead callout: the first divergence in plain language — instruction #, mnemonic,
 *      register, expected vs got (decimal + hex, copyable).
 *   3. Instruction trace: every compared instruction in order. Passing rows are
 *      condensed/dimmed; the diverging row is highlighted and expanded with the
 *      expected/got comparison. Branch/PC mismatches (golden/dut null, register "PC")
 *      are handled by reading values from the mismatch object.
 */
import Badge from '../primitives/Badge'
import CopyButton from '../primitives/CopyButton'
import Drawer from '../primitives/Drawer'
import Tooltip from '../primitives/Tooltip'
import { firstDivergence, formatHex } from '../../data/metrics'
import styles from './TestDetailDrawer.module.css'

function RegChip({ role, name, hint }) {
  if (!name) return null
  return (
    <Tooltip label={hint} side="bottom">
      <span className={styles.reg}>
        <span className={styles.regRole}>{role}</span>
        <span className="u-mono">{name}</span>
      </span>
    </Tooltip>
  )
}

function ValueCompare({ mismatch, golden, dut }) {
  // Register writes carry golden/dut; branch/PC mismatches carry values on mismatch.
  const expected = golden ?? mismatch?.expected ?? null
  const got = dut ?? mismatch?.got ?? null
  return (
    <div className={styles.compare}>
      <div className={styles.compareCol}>
        <div className={styles.compareLabel}>Expected (golden)</div>
        <CopyButton value={expected}>
          <span className={`u-mono ${styles.expected}`}>{expected}</span>
        </CopyButton>
        <CopyButton value={formatHex(expected)}>
          <span className={`u-mono ${styles.hex}`}>{formatHex(expected)}</span>
        </CopyButton>
      </div>
      <div className={styles.compareCol}>
        <div className={styles.compareLabel}>Got (DUT)</div>
        <CopyButton value={got}>
          <span className={`u-mono ${styles.got}`}>{got}</span>
        </CopyButton>
        <CopyButton value={formatHex(got)}>
          <span className={`u-mono ${styles.hex}`}>{formatHex(got)}</span>
        </CopyButton>
      </div>
    </div>
  )
}

function InstructionRow({ instr }) {
  const failed = !instr.passed
  return (
    <li className={`${styles.instr} ${failed ? styles.instrFailed : styles.instrPass}`}>
      <div className={styles.instrHead}>
        <span className={styles.instrNum}>#{instr.instrNumber}</span>
        <span className={`u-mono ${styles.mnemonic}`}>{instr.mnemonic}</span>
        <span className={styles.regs}>
          <RegChip role="rd" name={instr.registers?.rd} hint="Destination register" />
          <RegChip role="rs1" name={instr.registers?.rs1} hint="Source register 1" />
          <RegChip role="rs2" name={instr.registers?.rs2} hint="Source register 2" />
          {instr.imm != null && (
            <Tooltip label="Immediate operand" side="bottom">
              <span className={styles.reg}>
                <span className={styles.regRole}>imm</span>
                <span className="u-mono">{instr.imm}</span>
              </span>
            </Tooltip>
          )}
        </span>
        <span className={styles.instrStatus}>
          <Badge variant={instr.passed ? 'pass' : 'fail'} withIcon>
            {instr.passed ? 'Match' : instr.mismatch?.register ?? 'Mismatch'}
          </Badge>
        </span>
      </div>
      {failed && <ValueCompare mismatch={instr.mismatch} golden={instr.goldenValue} dut={instr.dutValue} />}
    </li>
  )
}

export default function TestDetailDrawer({ open, onClose, test, run }) {
  if (!test) return <Drawer open={open} onClose={onClose} title="" />

  const lead = firstDivergence(test)
  const leadExpected = lead?.goldenValue ?? lead?.mismatch?.expected ?? null
  const leadGot = lead?.dutValue ?? lead?.mismatch?.got ?? null

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={<span className="u-mono">{test.testName}</span>}
      subtitle={
        <span className={styles.subtitle}>
          <span>{run?.rtlDir}</span>
          {run?.mutationLabel && <Badge variant="mutation">{run.mutationLabel}</Badge>}
        </span>
      }
    >
      <div className={styles.statusRow}>
        <Badge variant={test.passed ? 'pass' : 'fail'} withIcon>
          {test.passed ? 'All instructions matched' : 'Diverged from golden model'}
        </Badge>
      </div>

      {lead && (
        <div className={styles.callout}>
          <div className={styles.calloutTitle}>
            First divergence at instruction #{lead.instrNumber} (<span className="u-mono">{lead.mnemonic}</span>)
          </div>
          <p className={styles.calloutBody}>
            Register <span className="u-mono u-strong">{lead.mismatch?.register}</span> expected{' '}
            <span className="u-mono">{leadExpected}</span> ({formatHex(leadExpected)}), got{' '}
            <span className={`u-mono ${styles.got}`}>{leadGot}</span> ({formatHex(leadGot)}).
          </p>
        </div>
      )}

      <div className={styles.traceHead}>
        Instruction trace
        <span className="u-faint"> · {test.instructions.length} compared</span>
      </div>
      <ol className={styles.trace}>
        {test.instructions.map((instr) => (
          <InstructionRow key={instr.instrNumber} instr={instr} />
        ))}
      </ol>
    </Drawer>
  )
}
