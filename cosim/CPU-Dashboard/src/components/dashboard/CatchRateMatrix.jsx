/*
 * Catch-rate matrix (roadmap step 7): rows are mutation runs (injected bugs),
 * columns are programs. A cell is "caught" when that program's test failed under
 * the bug, "slipped" when it passed (the bug went undetected by that program), or
 * "absent" when the program wasn't run. The eye should land on red — a bug that
 * slipped past every program (a coverage gap) is the thing worth noticing.
 */
import Tooltip from '../primitives/Tooltip'
import styles from './CatchRateMatrix.module.css'

const CELL_HINT = {
  caught: 'Caught — this program failed, detecting the bug',
  slipped: 'Slipped — this program passed despite the bug',
  absent: 'Not run for this bug',
}

export default function CatchRateMatrix({ matrix }) {
  const { programs, rows } = matrix

  return (
    <div className={styles.scroll}>
      <table className={styles.matrix}>
        <thead>
          <tr>
            <th className={styles.corner}>Bug \ Program</th>
            {programs.map((p) => (
              <th key={p} className={styles.colHead}>
                <span className="u-mono">{p}</span>
              </th>
            ))}
            <th className={styles.rateHead}>
              <Tooltip label="Programs that caught this bug ÷ programs run" side="bottom">
                <span>Catch rate</span>
              </Tooltip>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.runId}>
              <th scope="row" className={styles.rowHead}>
                <Tooltip label={row.rtlDir} side="right">
                  <span className="u-mono">{row.mutationLabel}</span>
                </Tooltip>
              </th>
              {row.cells.map((cell) => (
                <td key={cell.program} className={styles.cell}>
                  <Tooltip label={CELL_HINT[cell.state]} side="top">
                    <span className={`${styles.dot} ${styles[cell.state]}`}>
                      {cell.state === 'caught' ? '✓' : cell.state === 'slipped' ? '·' : ''}
                    </span>
                  </Tooltip>
                </td>
              ))}
              <td className={styles.rate}>
                <span className={styles.rateBarTrack}>
                  <span
                    className={styles.rateBarFill}
                    style={{ width: `${row.catchRate}%` }}
                    data-zero={row.catchRate === 0}
                  />
                </span>
                <span className={styles.rateNum}>
                  {row.caughtCount}/{row.programCount}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
