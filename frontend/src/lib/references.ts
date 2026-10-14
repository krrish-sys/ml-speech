/**
 * Reference speeches registered in datasets/rights/*.json and datasets/registry/sources.yaml.
 * Only the Gettysburg passage text is bundled; for the others the user pastes the passage.
 */
export interface ReferenceSpeech {
  id: string
  title: string
  speaker: string
  license: string
  text: string
}

export const GETTYSBURG_OPENING =
  'Four score and seven years ago our fathers brought forth on this continent, a new nation, conceived in Liberty, and dedicated to the proposition that all men are created equal. Now we are engaged in a great civil war, testing whether that nation, or any nation so conceived and so dedicated, can long endure.'

export const REFERENCES: ReferenceSpeech[] = [
  {
    id: 'asset-07',
    title: 'Gettysburg Address (opening)',
    speaker: 'LibriVox volunteer reading',
    license: 'Public domain',
    text: GETTYSBURG_OPENING,
  },
  { id: 'asset-10', title: 'Evil Empire Speech', speaker: 'Ronald Reagan', license: 'Public domain', text: '' },
  { id: 'asset-11', title: 'Resignation Address', speaker: 'Richard Nixon', license: 'Public domain', text: '' },
  { id: 'custom', title: 'My own passage', speaker: 'No reference speaker', license: '—', text: '' },
]

export const PRACTICE_PASSAGES: string[] = [
  'The future does not belong to those who wait for certainty. It belongs to those who have the courage to take the first step when the path ahead is still obscured. We must build with purpose, speak with clarity, and lead with empathy.',
  'Over the past three quarters, our operational efficiency improved by twenty-four percent while customer retention reached an all-time high. The key driver was not cutting corners, but streamlining cross-functional alignment and prioritizing high-leverage product initiatives.',
  'Complex systems fail in complex ways. By isolating state, eliminating hidden dependencies, and enforcing deterministic contracts across services, we turn unpredictable failures into observable, self-healing events.',
  'When our deployment pipeline experienced an unexpected outage during peak hours, I immediately convened our incident response squad, established clear communication channels, and rolled back the offending migration within eight minutes.',
  'Global markets stabilized today as central banks signaled a pause in interest rate hikes, pointing to cooling consumer inflation. In technology, renewable infrastructure investments surged past quarterly projections across North America and Europe.',
  'The measure of true innovation is not whether a technology can be built, but whether it serves the genuine welfare of the society that sustains it. Progress without accountability is merely disruption without direction.',
  'The wind howled across the ridge as the fog began to settle over the valley. In the distance, a solitary light flickered through the pine trees, reminding us that no matter how treacherous the climb, warmth was waiting at the summit.',
  'We choose to go to the moon in this decade and do the other things, not because they are easy, but because they are hard, because that goal will serve to organize and measure the best of our energies and skills.',
  'Recent observations from deep-space telescopes have revealed atmospheric signatures on distant exoplanets that defy our previous models. Every discovery reminds us that the universe is far richer and more nuanced than our textbooks suggest.',
  'A great team is not defined by an absence of obstacles, but by the resilience with which they confront them. When everyone shares a common vision and trusts each other completely, even insurmountable challenges become milestones.',
]

